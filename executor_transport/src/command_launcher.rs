//! Single-threaded, separate-process privilege boundary for Bash commands.

use std::ffi::{CStr, CString, OsStr};
use std::io;
use std::os::unix::ffi::OsStrExt;

pub fn launch(command: &OsStr) -> io::Result<()> {
    let command = CString::new(command.as_bytes())?;
    let configured_limit = std::env::var_os("PWC_CHAT_SANDBOX_PIDS_MAX");
    let limit = process_limit(
        configured_limit
            .as_ref()
            .map(|value| {
                value.to_str().ok_or_else(|| {
                    io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "invalid executor process limit",
                    )
                })
            })
            .transpose()?,
    )?;
    // Called before the Tokio runtime or any application threads are created.
    demote(c"pwc-chat", limit)?;
    unsafe {
        // Match Python's startup signal dispositions before its os.execv call.
        for signal in [libc::SIGPIPE, libc::SIGXFSZ] {
            if libc::signal(signal, libc::SIG_IGN) == libc::SIG_ERR {
                return Err(io::Error::last_os_error());
            }
        }
        let argv = [
            c"/bin/bash".as_ptr(),
            c"-lc".as_ptr(),
            command.as_ptr(),
            std::ptr::null(),
        ];
        libc::execv(c"/bin/bash".as_ptr(), argv.as_ptr());
    }
    Err(io::Error::last_os_error())
}

fn process_limit(value: Option<&str>) -> io::Result<libc::rlim_t> {
    let value = value.unwrap_or("64").trim().parse::<u64>().ok();
    match value {
        Some(value @ 16..=512) => Ok(value as libc::rlim_t),
        _ => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid executor process limit",
        )),
    }
}

fn demote(user: &CStr, limit: libc::rlim_t) -> io::Result<()> {
    // getpwnam's static storage is safe here: this is a single-threaded launcher.
    unsafe {
        let account = libc::getpwnam(user.as_ptr());
        if account.is_null() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                "executor account unavailable",
            ));
        }
        let uid = (*account).pw_uid;
        let gid = (*account).pw_gid;
        if uid == 0 || gid == 0 {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "executor account must be unprivileged",
            ));
        }
        if libc::setgroups(0, std::ptr::null()) != 0
            || libc::setgid(gid) != 0
            || libc::setuid(uid) != 0
        {
            return Err(io::Error::last_os_error());
        }
        libc::umask(0o077);
        let limits = libc::rlimit {
            rlim_cur: limit,
            rlim_max: limit,
        };
        if libc::setrlimit(libc::RLIMIT_NPROC, &limits) != 0
            || libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) != 0
        {
            return Err(io::Error::last_os_error());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;

    #[test]
    fn limits_match_the_settings_contract() {
        for (input, expected) in [(None, 64), (Some("16"), 16), (Some(" 512 "), 512)] {
            assert_eq!(process_limit(input).unwrap(), expected);
        }
        for value in ["", "0", "15", "513", "-1", "1.5", "18446744073709551616"] {
            assert!(process_limit(Some(value)).is_err());
        }
    }

    #[test]
    fn privilege_transitions_in_isolated_children() {
        if unsafe { libc::geteuid() } != 0 {
            return;
        }
        for case in ["success", "missing", "unprivileged", "limit_failure"] {
            let result = Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "command_launcher::tests::privilege_child",
                    "--nocapture",
                ])
                .env("PWC_PRIVILEGE_TEST_CASE", case)
                .output()
                .unwrap();
            assert!(
                result.status.success(),
                "{case}: {}",
                String::from_utf8_lossy(&result.stderr)
            );
        }
    }

    #[test]
    fn privilege_child() {
        let Ok(case) = std::env::var("PWC_PRIVILEGE_TEST_CASE") else {
            return;
        };
        match case.as_str() {
            "missing" => {
                assert!(demote(c"pwc-account-that-does-not-exist", 64).is_err());
                assert_eq!(unsafe { libc::geteuid() }, 0);
            }
            "unprivileged" => unsafe {
                assert_eq!(libc::setuid(65534), 0);
                assert!(demote(c"nobody", 64).is_err());
            },
            "limit_failure" => unsafe {
                let limits = libc::rlimit {
                    rlim_cur: 32,
                    rlim_max: 32,
                };
                assert_eq!(libc::setrlimit(libc::RLIMIT_NPROC, &limits), 0);
                assert!(demote(c"nobody", 64).is_err());
            },
            "success" => unsafe {
                let account = libc::getpwnam(c"nobody".as_ptr());
                assert!(!account.is_null());
                let (uid, gid) = ((*account).pw_uid, (*account).pw_gid);
                demote(c"nobody", 64).unwrap();
                let (mut real, mut effective, mut saved) = (0, 0, 0);
                assert_eq!(libc::getresuid(&mut real, &mut effective, &mut saved), 0);
                assert_eq!((real, effective, saved), (uid, uid, uid));
                assert_eq!(libc::getresgid(&mut real, &mut effective, &mut saved), 0);
                assert_eq!((real, effective, saved), (gid, gid, gid));
                assert_eq!(libc::getgroups(0, std::ptr::null_mut()), 0);
                assert_eq!(libc::umask(0o077), 0o077);
                let mut limits = libc::rlimit {
                    rlim_cur: 0,
                    rlim_max: 0,
                };
                assert_eq!(libc::getrlimit(libc::RLIMIT_NPROC, &mut limits), 0);
                assert_eq!((limits.rlim_cur, limits.rlim_max), (64, 64));
                assert_eq!(libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0), 0);
                assert_ne!(libc::setuid(0), 0);
            },
            _ => panic!("unknown privilege test case"),
        }
    }
}
