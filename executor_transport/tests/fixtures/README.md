These deliberately public DER fixtures form a self-signed localhost server
identity for the startup connector's untrusted-certificate rejection test.
They are not deployment credentials and are not trusted by the client.

The certificate uses ECDSA P-256, SAN `DNS:localhost`, and
`basicConstraints=critical,CA:FALSE`. The key is unencrypted PKCS#8 DER.
