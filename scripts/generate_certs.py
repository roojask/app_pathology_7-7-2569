import datetime
import os
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import socket

def generate_self_signed_cert(cert_dir="configs"):
    """
    Generates a self-signed SSL certificate and private key.
    Saves them as cert.pem and key.pem in the specified directory.
    """
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = Path(cert_dir) / "cert.pem"
    key_path = Path(cert_dir) / "key.pem"
    
    if cert_path.exists() and key_path.exists():
        print(f"[*] SSL Certificates already exist at {cert_path} and {key_path}")
        return True
        
    print("[*] Generating new self-signed SSL certificate...")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Generate public certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "TH"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Bangkok"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Bangkok"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Pathology"),
        x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1"),
    ])
    
    # Try to resolve local IP to put in SAN (Subject Alternative Name)
    ip_addresses = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if local_ip and local_ip != "127.0.0.1":
            ip_addresses.append(local_ip)
    except Exception:
        pass
        
    import ipaddress
    san_list = [x509.DNSName("localhost")]
    for ip in ip_addresses:
        san_list.append(x509.IPAddress(ipaddress.ip_address(ip)))
        
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow() - datetime.timedelta(days=1)
    ).not_valid_after(
        # Valid for 10 years
        datetime.datetime.utcnow() + datetime.timedelta(days=365 * 10)
    ).add_extension(
        x509.SubjectAlternativeName(san_list),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    # Write private key
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        
    # Write certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
        
    print(f"[+] SSL Certificates successfully generated at:")
    print(f"    - Certificate: {cert_path}")
    print(f"    - Private Key: {key_path}")
    return True

if __name__ == "__main__":
    generate_self_signed_cert()
