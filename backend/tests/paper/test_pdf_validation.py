"""
Test PDF validation logic for detecting invalid files (HTML, reCAPTCHA, etc.)
"""

import sys

sys.path.insert(0, "/root/python_projects/paperswithcode")

from backend.utils.pdf_utils import _is_valid_pdf


def test_valid_pdf():
    """Test that a valid PDF is recognized."""
    # Minimal valid PDF content
    content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"x" * 2000 + b"\n%%EOF"
    is_valid, error_msg = _is_valid_pdf(content)
    assert is_valid, f"Valid PDF not recognized: {error_msg}"
    print("✅ Valid PDF recognized")


def test_html_recaptcha():
    """Test that HTML with reCAPTCHA is detected."""
    content = b"""<!DOCTYPE html>
<html>
<head><title>reCAPTCHA</title></head>
<body>
<div id="recaptcha"></div>
</body>
</html>"""
    is_valid, error_msg = _is_valid_pdf(content)
    assert not is_valid, "reCAPTCHA HTML should be invalid"
    assert "recaptcha" in error_msg.lower(), (
        f"Error message should mention reCAPTCHA: {error_msg}"
    )
    print(f"✅ reCAPTCHA detected: {error_msg}")


def test_html_without_recaptcha():
    """Test that regular HTML is detected."""
    content = b"""<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body>Something went wrong</body>
</html>"""
    is_valid, error_msg = _is_valid_pdf(content)
    assert not is_valid, "HTML should be invalid"
    assert "html page" in error_msg.lower(), (
        f"Error message should mention HTML: {error_msg}"
    )
    print(f"✅ HTML detected: {error_msg}")


def test_missing_magic_bytes():
    """Test that files without PDF magic bytes are rejected."""
    content = b"This is not a PDF" + b"x" * 2000
    is_valid, error_msg = _is_valid_pdf(content)
    assert not is_valid, "Non-PDF should be invalid"
    assert "magic bytes" in error_msg.lower(), (
        f"Error message should mention magic bytes: {error_msg}"
    )
    print(f"✅ Missing magic bytes detected: {error_msg}")


def test_truncated_pdf():
    """Test that truncated PDFs are detected."""
    content = b"%PDF-1.4\n" + b"x" * 2000  # Missing %%EOF
    is_valid, error_msg = _is_valid_pdf(content)
    assert not is_valid, "Truncated PDF should be invalid"
    assert "truncated" in error_msg.lower() or "eof" in error_msg.lower(), (
        f"Error message should mention truncation: {error_msg}"
    )
    print(f"✅ Truncated PDF detected: {error_msg}")


def test_too_small_file():
    """Test that files smaller than 1KB are rejected."""
    content = b"%PDF-1.4\n" + b"x" * 100 + b"\n%%EOF"  # Only ~120 bytes
    is_valid, error_msg = _is_valid_pdf(content)
    assert not is_valid, "Too-small file should be invalid"
    assert "too small" in error_msg.lower(), (
        f"Error message should mention size: {error_msg}"
    )
    print(f"✅ Small file detected: {error_msg}")


def test_captcha_variant():
    """Test that CAPTCHA (without 're' prefix) is also detected."""
    content = b"""<html>
<body>
<div class="g-captcha">Please verify you are human</div>
</body>
</html>"""
    is_valid, error_msg = _is_valid_pdf(content)
    assert not is_valid, "CAPTCHA HTML should be invalid"
    # Should be caught as HTML first, then checked for captcha
    print(f"✅ CAPTCHA variant detected: {error_msg}")


if __name__ == "__main__":
    print("🧪 Testing PDF validation logic...\n")

    test_valid_pdf()
    test_html_recaptcha()
    test_html_without_recaptcha()
    test_missing_magic_bytes()
    test_truncated_pdf()
    test_too_small_file()
    test_captcha_variant()

    print("\n✅ All PDF validation tests passed!")
