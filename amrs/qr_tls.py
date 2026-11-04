"""Certificate setup for HTTPS camera check-in on a campus network or local pilot."""

import ipaddress
import secrets
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .mail_delivery import _crypt
from .paths import profile_root

PRIVATE_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")


def private_address(host):
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        raise ValueError(
            "Enter this computer’s private Wi-Fi IPv4 address for local setup."
        ) from None
    if not any(
        address in ipaddress.ip_network(network) for network in PRIVATE_NETWORKS
    ):
        raise ValueError("Local setup needs a private Wi-Fi IPv4 address.")
    return address


def certificate_builder(subject, issuer, public_key, start, end):
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
    )


def ca_extensions(builder, key, path_length):
    return (
        builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=path_length), critical=True
        )
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, None, None),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
    )


def server_certificate(address, issuer, leaf_key, issuer_key, start, end):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(address))])
    return (
        certificate_builder(subject, issuer, leaf_key.public_key(), start, end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(address)]), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )


def key_bytes(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def create_reusable_certificate(host):
    """Create an opt-in classroom trust profile. The root key is never written."""
    address = private_address(host)
    now = datetime.now(UTC)
    start, end = now - timedelta(minutes=5), now + timedelta(days=30)
    suffix = secrets.token_hex(6)
    root_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "AMRS Classroom " + suffix)]
    )
    issuer_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "AMRS QR LAN " + suffix)]
    )
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root = ca_extensions(
        certificate_builder(root_name, root_name, root_key.public_key(), start, end),
        root_key,
        1,
    ).sign(root_key, hashes.SHA256())
    issuer = (
        ca_extensions(
            certificate_builder(
                issuer_name, root_name, issuer_key.public_key(), start, end
            ),
            issuer_key,
            0,
        )
        .add_extension(
            x509.NameConstraints(
                permitted_subtrees=[
                    *(
                        x509.IPAddress(ipaddress.ip_network(n))
                        for n in PRIVATE_NETWORKS
                    ),
                    x509.DNSName("amrs.invalid"),
                ],
                excluded_subtrees=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    leaf = server_certificate(
        address,
        issuer_name,
        leaf_key,
        issuer_key,
        start,
        min(end, now + timedelta(days=7)),
    )
    folder = profile_root() / "qr-https" / suffix
    folder.mkdir(parents=True)
    cert, key, phone = (
        folder / name for name in ("server.pem", "server-key.pem", "AMRS-QR-Trust.cer")
    )
    key.write_bytes(key_bytes(leaf_key))
    cert.write_bytes(
        leaf.public_bytes(serialization.Encoding.PEM)
        + issuer.public_bytes(serialization.Encoding.PEM)
    )
    phone.write_bytes(root.public_bytes(serialization.Encoding.DER))
    (folder / "issuer.pem").write_bytes(issuer.public_bytes(serialization.Encoding.PEM))
    (folder / "issuer.dpapi").write_bytes(_crypt(key_bytes(issuer_key)))
    return cert, key, phone, root.fingerprint(hashes.SHA256()).hex(":").upper()


def reusable_folder(cert, key):
    if not cert or not key:
        return None
    cert, key = Path(cert).resolve(), Path(key).resolve()
    folder = cert.parent
    if (
        cert.name == "server.pem"
        and key == folder / "server-key.pem"
        and folder.parent == (profile_root() / "qr-https").resolve()
        and (folder / "issuer.dpapi").is_file()
        and (folder / "issuer.pem").is_file()
    ):
        return folder
    return None


def reusable_tls_context(folder, host):
    address = private_address(host)
    now = datetime.now(UTC)
    try:
        issuer_pem = (folder / "issuer.pem").read_bytes()
        issuer = x509.load_pem_x509_certificate(issuer_pem)
    except OSError, ValueError:
        raise ValueError(
            "The classroom HTTPS profile is unavailable. Open HTTPS setup."
        ) from None
    if not issuer.not_valid_before_utc <= now < issuer.not_valid_after_utc:
        raise ValueError(
            "The classroom trust certificate expired. Create a new one in HTTPS setup."
        )
    key = folder / "server-key.pem"
    cert = folder / (f"server-{address}.pem")
    if cert.exists():
        try:
            return tls_context(cert, key, host)
        except ValueError:
            pass  # Renew an expired or interrupted leaf under the same trust root.
    try:
        issuer_key = serialization.load_pem_private_key(
            _crypt((folder / "issuer.dpapi").read_bytes(), True), None
        )
        leaf_key = serialization.load_pem_private_key(key.read_bytes(), None)
        leaf = server_certificate(
            address,
            issuer.subject,
            leaf_key,
            issuer_key,
            max(issuer.not_valid_before_utc, now - timedelta(minutes=5)),
            min(issuer.not_valid_after_utc, now + timedelta(days=7)),
        )
        leaf.verify_directly_issued_by(issuer)
        temporary = cert.with_name(f"{cert.name}.{secrets.token_hex(5)}.tmp")
        try:
            temporary.write_bytes(
                leaf.public_bytes(serialization.Encoding.PEM) + issuer_pem
            )
            temporary.replace(cert)
        finally:
            temporary.unlink(missing_ok=True)
        return tls_context(cert, key, host)
    except OSError, ValueError, TypeError:
        raise ValueError(
            "Could not renew the classroom HTTPS certificate. Open HTTPS setup."
        ) from None


def tls_context(cert, key, host):
    if not cert or not key:
        raise ValueError(
            "Secure QR needs a trusted HTTPS certificate and private key. Open HTTPS setup."
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(cert, key, password=lambda: "")
        leaf = x509.load_pem_x509_certificates(Path(cert).read_bytes())[0]
        names = leaf.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except OSError, ssl.SSLError, ValueError, IndexError, x509.ExtensionNotFound:
        raise ValueError(
            "Use matching HTTPS PEM files with a subject alternative name for the QR address."
        ) from None
    now = datetime.now(UTC)
    if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
        raise ValueError("The HTTPS certificate is expired or not valid yet.")
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        matched = any(
            host == name.lower()
            or (name.startswith("*.") and host.partition(".")[2] == name[2:].lower())
            for name in names.get_values_for_type(x509.DNSName)
        )
    else:
        matched = address in names.get_values_for_type(x509.IPAddress)
    if not matched:
        raise ValueError(
            "The HTTPS certificate does not cover the QR address. Use the address on the certificate."
        )
    return context


def make_local_certificate(host):
    """Generate a short-lived root constrained to one LAN IP, and discard its key."""
    address = private_address(host)
    now = datetime.now(UTC)
    start, end = now - timedelta(minutes=5), now + timedelta(days=30)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AMRS QR " + host)])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def certificate(subject, issuer, public_key):
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(start)
            .not_valid_after(end)
        )

    ca = (
        certificate(ca_name, ca_name, ca_key.public_key())
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, None, None),
            critical=True,
        )
        .add_extension(
            x509.NameConstraints(
                permitted_subtrees=[
                    x509.IPAddress(ipaddress.ip_network(f"{address}/32"))
                ],
                excluded_subtrees=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        certificate(leaf_name, ca_name, leaf_key.public_key())
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(address)]), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    folder = profile_root() / "qr-https" / secrets.token_hex(8)
    folder.mkdir(parents=True)
    cert, key, phone = (
        folder / filename
        for filename in ("server.pem", "server-key.pem", "AMRS-QR-Trust.cer")
    )
    cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    phone.write_bytes(ca.public_bytes(serialization.Encoding.DER))
    return cert, key, phone, ca.fingerprint(hashes.SHA256()).hex(":").upper()
