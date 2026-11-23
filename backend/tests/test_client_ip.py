import pytest
from django.test import RequestFactory

from whileisleep.client_ip import client_ip


def request_from(remote="203.0.113.9", forwarded=None):
    headers = {"X-Forwarded-For": forwarded} if forwarded is not None else {}
    return RequestFactory().get("/", REMOTE_ADDR=remote, headers=headers)


def test_without_proxies_the_header_is_ignored(settings):
    settings.TRUSTED_PROXY_COUNT = 0
    assert client_ip(request_from(forwarded="1.2.3.4")) == "203.0.113.9"


def test_one_proxy_takes_the_last_entry(settings):
    settings.TRUSTED_PROXY_COUNT = 1
    # The proxy appended 198.51.100.7; "1.2.3.4" is what the client claimed.
    assert client_ip(request_from(remote="10.0.0.2", forwarded="1.2.3.4, 198.51.100.7")) == "198.51.100.7"


def test_two_proxies_take_the_second_from_the_right(settings):
    settings.TRUSTED_PROXY_COUNT = 2
    request = request_from(remote="10.0.0.2", forwarded="1.2.3.4, 198.51.100.7, 10.0.0.3")
    assert client_ip(request) == "198.51.100.7"


@pytest.mark.parametrize("forwarded", [None, "", "not-an-ip", "198.51.100.7'; DROP TABLE"])
def test_missing_or_bad_header_falls_back_to_the_socket(settings, forwarded):
    settings.TRUSTED_PROXY_COUNT = 1
    assert client_ip(request_from(remote="10.0.0.2", forwarded=forwarded)) == "10.0.0.2"


def test_fewer_hops_than_proxies_falls_back(settings):
    settings.TRUSTED_PROXY_COUNT = 2
    assert client_ip(request_from(remote="10.0.0.2", forwarded="198.51.100.7")) == "10.0.0.2"
