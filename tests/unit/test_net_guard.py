"""Tests for SSRF net_guard: private/loopback/link-local blocked, multi-redirect, opt-in CIDR."""

import pytest
from unittest.mock import patch, MagicMock
import socket

from security.net_guard import (
    validate_url, validate_redirect_url, SSRFBlocked, _is_ip_blocked,
    _BLOCKED_NETWORKS,
)


class TestNetGuard:
    """Net guard blocks private/loopback/link-local URLs."""

    def test_http_allowed(self):
        url = validate_url("https://example.com")
        assert url == "https://example.com"

    def test_ftp_blocked(self):
        with pytest.raises(SSRFBlocked, match="Blocked URL scheme"):
            validate_url("ftp://example.com/file")

    def test_credentials_blocked(self):
        with pytest.raises(SSRFBlocked, match="credentials"):
            validate_url("https://user:pass@example.com")

    def test_localhost_blocked(self):
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_url("http://localhost/admin")

    def test_loopback_ip_blocked(self):
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_url("http://127.0.0.1/admin")

    def test_0_0_0_0_blocked(self):
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_url("http://0.0.0.0/admin")

    def test_private_10_x_blocked(self):
        with patch("security.net_guard.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, 0, 0, '', ('10.0.0.1', 0))]
            with pytest.raises(SSRFBlocked, match="Blocked IP"):
                validate_url("http://internal.corp/admin")

    def test_private_192_168_x_blocked(self):
        with patch("security.net_guard.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, 0, 0, '', ('192.168.1.1', 0))]
            with pytest.raises(SSRFBlocked, match="Blocked IP"):
                validate_url("http://router.local/admin")

    def test_link_local_blocked(self):
        # metadata.google.internal is now in blocked hostnames, so it's caught before DNS
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_url("http://metadata.google.internal/admin")

    def test_cloud_metadata_ip_blocked(self):
        # 169.254.169.254 is in blocked hostnames, so it's caught before DNS
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_cloud_metadata_gcp_blocked(self):
        # 169.254.169.253 is in blocked hostnames
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_url("http://169.254.169.253/computeMetadata/v1/")

    def test_cloud_metadata_ip_resolves_blocked(self):
        """IP that resolves to cloud metadata is caught at DNS resolution."""
        with patch("security.net_guard.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, 0, 0, '', ('169.254.169.254', 0))]
            with pytest.raises(SSRFBlocked, match="Blocked IP"):
                validate_url("http://some-internal-host.example.com/meta-data/")

    def test_dns_failure_blocked(self):
        with patch("security.net_guard.socket.getaddrinfo") as mock_dns:
            mock_dns.side_effect = socket.gaierror("DNS failure")
            with pytest.raises(SSRFBlocked, match="DNS resolution failed"):
                validate_url("http://nonexistent.invalid")

    def test_redirect_to_private_blocked(self):
        with pytest.raises(SSRFBlocked, match="Blocked hostname"):
            validate_redirect_url("http://127.0.0.1/secret", "https://example.com")

    def test_redirect_to_loopback_blocked(self):
        with pytest.raises(SSRFBlocked, match="Blocked IP|Blocked hostname"):
            validate_redirect_url("http://10.0.0.1/secret", "https://example.com")


class TestNetGuardOptInCIDR:
    """Opt-in CIDR allowlist permits specific private ranges."""

    def test_opt_in_cidr_permits_private(self):
        with patch("security.net_guard.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                net_allow_private_networks=["192.168.1.0/24"],
            )
            with patch("security.net_guard.socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(socket.AF_INET, 0, 0, '', ('192.168.1.50', 0))]
                url = validate_url("http://homeassistant.local/api")
                assert url == "http://homeassistant.local/api"

    def test_opt_in_cidr_does_not_help_other_ranges(self):
        with patch("security.net_guard.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                net_allow_private_networks=["192.168.1.0/24"],
            )
            with patch("security.net_guard.socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(socket.AF_INET, 0, 0, '', ('10.0.0.5', 0))]
                with pytest.raises(SSRFBlocked, match="Blocked IP"):
                    validate_url("http://other-internal.corp/api")


class TestNetGuardIPBlocked:
    """Low-level _is_ip_blocked function."""

    def test_public_ip_not_blocked(self):
        assert _is_ip_blocked("8.8.8.8", []) is False

    def test_loopback_blocked(self):
        assert _is_ip_blocked("127.0.0.1", []) is True

    def test_private_10_blocked(self):
        assert _is_ip_blocked("10.0.0.1", []) is True

    def test_link_local_blocked(self):
        assert _is_ip_blocked("169.254.1.1", []) is True

    def test_invalid_ip_blocked(self):
        assert _is_ip_blocked("not-an-ip", []) is True

    def test_ula_ipv6_blocked(self):
        assert _is_ip_blocked("fd00::1", []) is True

    def test_loopback_ipv6_blocked(self):
        assert _is_ip_blocked("::1", []) is True

    def test_cloud_metadata_aws_blocked(self):
        assert _is_ip_blocked("169.254.169.254", []) is True

    def test_cloud_metadata_gcp_blocked(self):
        assert _is_ip_blocked("169.254.169.253", []) is True
