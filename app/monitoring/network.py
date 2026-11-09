"""Endereços IPv4 da rede local, para o operador configurar as modalidades."""

from __future__ import annotations

import ipaddress
import socket

import psutil

# Adaptadores que não são a LAN da clínica: VPN (inclusive o túnel WireGuard "VOXELVPN"),
# virtualização, contêineres e loopback. Comparação por trecho do nome, sem diferenciar caixa.
VIRTUAL_ADAPTER_MARKERS = (
    "voxelvpn",
    "wireguard",
    "wg",
    "vpn",
    "tap",
    "tun",
    "virtual",
    "vethernet",
    "hyper-v",
    "vmware",
    "vbox",
    "docker",
    "wsl",
    "loopback",
    "npcap",
    "tailscale",
    "zerotier",
    "bluetooth",
)


def is_virtual_adapter(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in VIRTUAL_ADAPTER_MARKERS)


def local_ipv4_addresses() -> list[str]:
    """IPv4 dos adaptadores físicos ativos; exclui loopback, APIPA (169.254/16) e adaptadores virtuais/VPN."""
    stats = psutil.net_if_stats()
    found: set[ipaddress.IPv4Address] = set()
    for name, addresses in psutil.net_if_addrs().items():
        if is_virtual_adapter(name) or not (stats.get(name) and stats[name].isup):
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.IPv4Address(address.address)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                continue
            found.add(ip)
    return [str(ip) for ip in sorted(found)]
