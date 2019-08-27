"""This module tests the BGP daemon"""

import pytest

from ipmininet.clean import cleanup
from ipmininet.examples.simple_bgp_network import SimpleBGPTopo
from ipmininet.examples.bgp_local_pref import BGPTopoLocalPref
from ipmininet.examples.bgp_med import BGPTopoMed
from ipmininet.examples.bgp_rr import BGPTopoRR
from ipmininet.examples.bgp_full_config import BGPTopoFull
from ipmininet.ipnet import IPNet
from ipmininet.iptopo import IPTopo
from ipmininet.router.config import BGP, bgp_peering, AS, iBGPFullMesh
from ipmininet.router.config.base import RouterConfig
from ipmininet.router.config.bgp import AF_INET, AF_INET6
from ipmininet.tests.utils import assert_connectivity, assert_path, traceroute
from . import require_root
from ipaddress import ip_address
import sys
import pexpect


class BGPTopo(IPTopo):

    def __init__(self, as2r1_params, *args, **kwargs):
        self.as2r1_params = as2r1_params
        super(BGPTopo, self).__init__(*args, **kwargs)

    def build(self, *args, **kwargs):
        """
           +----------+                                   +--------+
                      |                                   |
         AS1          |                  AS2              |        AS3
                      |                                   |
                      |                                   |
    +-------+   eBGP  |  +-------+     iBGP    +-------+  |  eBGP   +-------+
    | as1r1 +------------+ as2r1 +-------------+ as2r2 +------------+ as3r1 |
    +-------+         |  +-------+             +-------+  |         +-------+
                      |                                   |
                      |                                   |
                      |                                   |
         +------------+                                   +--------+
        """
        # Add all routers
        as1r1 = self.addRouter('as1r1', config=RouterConfig)
        as1r1.addDaemon(BGP, address_families=[AF_INET(redistribute=["connected"]),
                                               AF_INET6(redistribute=["connected"])])
        as2r1 = self.addRouter('as2r1', config=RouterConfig)
        as2r1.addDaemon(BGP, **self.as2r1_params)
        as2r2 = self.addRouter('as2r2', config=RouterConfig)
        as2r2.addDaemon(BGP, address_families=[AF_INET(redistribute=["connected"]),
                                               AF_INET6(redistribute=["connected"])])
        as3r1 = self.addRouter('as3r1', config=RouterConfig)
        as3r1.addDaemon(BGP, address_families=[AF_INET(redistribute=["connected"]),
                                               AF_INET6(redistribute=["connected"])])

        self.addLink(as1r1, as2r1, params1={"ip": ("10.1.1.1/24", "fd00:1:1::1/64")},
                     params2={"ip": ("10.1.1.2/24", "fd00:1:1::2/64")})
        self.addLink(as2r1, as2r2, params1={"ip": ("10.2.1.1/24", "fd00:2:1::1/64")},
                     params2={"ip": ("10.2.1.2/24", "fd00:2:1::2/64")})
        self.addLink(as3r1, as2r2, params1={"ip": ("10.3.1.1/24", "fd00:3:1::1/64")},
                     params2={"ip": ("10.3.1.2/24", "fd00:3:1::2/64")})

        # Set AS-ownerships
        self.addOverlay(AS(1, (as1r1,)))
        self.addOverlay(iBGPFullMesh(2, (as2r1, as2r2)))
        self.addOverlay(AS(3, (as3r1,)))
        # Add eBGP peering
        bgp_peering(self, as1r1, as2r1)
        bgp_peering(self, as3r1, as2r2)

        # Add test hosts
        self.addLink(as1r1, self.addHost('h%s' % as1r1), params1={"ip": ("10.1.0.1/24", "fd00:1::1/64")},
                     params2={"ip": ("10.1.0.2/24", "fd00:1::2/64")})
        self.addLink(as3r1, self.addHost('h%s' % as3r1), params1={"ip": ("10.3.0.1/24", "fd00:3::1/64")},
                     params2={"ip": ("10.3.0.2/24", "fd00:3::2/64")})
        super(BGPTopo, self).build(*args, **kwargs)


@require_root
def test_bgp_example():
    try:
        net = IPNet(topo=SimpleBGPTopo())
        net.start()
        assert_connectivity(net, v6=False)
        assert_connectivity(net, v6=True)
        net.stop()
    finally:
        cleanup()


@require_root
@pytest.mark.parametrize("bgp_params,expected_cfg", [
    ({"address_families": [AF_INET(redistribute=["connected"]), AF_INET6(redistribute=["connected"])]},
     ["router bgp 2",
      "    neighbor 10.1.1.1 remote-as 1",
      "    neighbor 10.2.1.2 remote-as 2",
      "    neighbor 10.1.1.1 ebgp-multihop",
      "    neighbor 10.1.1.1 activate",
      "    neighbor 10.2.1.2 activate",
      "    redistribute connected"]),
    ({"address_families": [AF_INET(redistribute=["connected"], networks=["10.0.0.0/24"]),
                           AF_INET6(redistribute=["connected"], networks=["fd00:2001:180::/64"])]},
     ["    network 10.0.0.0/24",
      "    network fd00:2001:180::/64"]),
])
def test_bgp_daemon_params(bgp_params, expected_cfg):
    try:
        net = IPNet(topo=BGPTopo(bgp_params), allocate_IPs=False)
        net.start()

        # Check generated configuration
        with open("/tmp/bgpd_as2r1.cfg") as fileobj:
            cfg = fileobj.readlines()
            for line in expected_cfg:
                assert (line + "\n") in cfg, "Cannot find the line '%s' in the generated configuration:\n%s"\
                                             % (line, "".join(cfg))

        # Check reachability
        assert_connectivity(net, v6=False)
        assert_connectivity(net, v6=True)
        net.stop()
    finally:
        cleanup()


config_ip1 = {
    'as1r1': [
        'fd00:1:1::1',
        'fd00:1:2::1'
    ],
    'as1r2': [
        'fd00:3:1::2',
        'fd00:4:1::1'
    ],
    'as1r3': [
        'fd00:1:2::2',
        'fd00:3:1::1',
        'fd00:3:2::1'
    ],
    'as1r4': [
        'fd00:4:1::2',
        'fd00:4:2::1'
    ],
    'as1r5': [
        'fd00:4:2::2',
        'fd00:5:2::2',
        'fd00:5:1::1'
    ],
    'as1r6': [
        'fd00:1:1::2',
        'fd00:3:2::2',
        'fd00:6:1::2',
        'fd00:5:1::2'
    ], 
    'as4r1': [
        'fd00:6:1::1',
        'dead:beef::1'
    ],
    'as4r2': [
        'fd00:5:2::1',
        'dead:beef::2'
    ],
    'as4h1': [
        'dead:beef::1',
        'dead:beef::2'
    ]
}


config_ip2 = {
    'as1r1': [
        'fd00:1:1::1',
        'fd00:1:2::1',
        'fd00:3:1::2'
    ],
    'as1r2': [
        'fd00:1:4::2',
        'd00:1:5::1'
    ],
    'as1r3': [
        'fd00:1:2::2',
        'fd00:1:4::1',
        'fd00:1:3::1'
    ],
    'as1r4': [
        'fd00:1:5::2',
        'fd00:1:6::1',
        'fd00:4:1::2'
    ],
    'as1r5': [
        'fd00:1:6::2',
        'fd00:1:7::1',
        'fd00:4:2::2'
    ],
    'as1r6': [
        'fd00:1:1::2',
        'fd00:1:3::2',
        'fd00:1:7::2',
        'fd00:5:1::2'
    ],
    'as2r1': [
        'fd00:2:1::2',
        'fd00:2:2::1',
        'dead:beef::1'
    ],
    'as2h1': [
        'dead:beef::2'
    ],
    'as3r1': [
        'fd00:3:1::1',
        'fd00:5:2::1'
    ],
    'as5r1': [
        'fd00:5:1::1',
        'fd00:5:2::2',
        'fd00:2:1::1'
    ],
    'as4r1': [
        'fd00:4:2::1',
        'fd00:2:2::2',
        'fd00:4:3::1'
    ], 
    'as4r2': [
        'fd00:4:1::1',
        'fd00:4:3::2'
    ]
}


local_pref_paths = [
    ['as1r1', 'as1r6', 'dead:beef::'],
    ['as1r2', 'as1r3', 'as1r6', 'dead:beef::'],
    ['as1r3', 'as1r6', 'dead:beef::'],
    ['as1r4', 'as1r5', 'as1r6', 'dead:beef::'],
    ['as1r5', 'as1r6', 'dead:beef::'],
    ['as1r6', 'dead:beef::']
]


@require_root
def test_bgp_local_pref():
    try:
        net = IPNet(topo=BGPTopoLocalPref())
        net.start()
        for path in local_pref_paths:
            assert_path_bgp(net, path, config_ip1)
        net.stop()
    finally:
        cleanup()


med_paths = [
    ['as1r1', 'as1r6', 'as1r5', 'dead:beef::'],
    ['as1r2', 'as1r4', 'as1r5', 'dead:beef::'],
    ['as1r3', 'as1r6', 'as1r5', 'dead:beef::'],
    ['as1r4', 'as1r5', 'dead:beef::'],
    ['as1r5', 'dead:beef::'],
    ['as1r6', 'as1r5', 'dead:beef::']
]


@require_root
def test_bgp_med():
    try:
        net = IPNet(topo=BGPTopoMed())
        net.start()
        for path in med_paths:
            assert_path_bgp(net, path, config_ip1)
        net.stop()
    finally:
        cleanup()


rr_paths = [
    ['as1r1', 'as1r6', 'as5r1', 'dead:beef::'],
    ['as1r2', 'as1r4', 'as4r2', 'as4r1', 'dead:beef::'],
    # ['as1r3', 'as1r1, 'as1r6', 'as5r1', 'dead:beef::'], to fix
    ['as1r4', 'as4r2', 'as4r1', 'dead:beef::'],
    ['as1r5', 'as4r1', 'dead:beef::'],
    ['as1r6', 'as5r1', 'dead:beef::']
]


@require_root
def test_bgp_rr():
    try:
        net = IPNet(topo=BGPTopoRR())
        net.start()
        for path in rr_paths:
            assert_path_bgp(net, path, config_ip2)
        net.stop()
    finally:
        cleanup()


full_paths = [
    ['as1r1', 'as1r3', 'as1r6', 'dead:beef::'],
    ['as1r2', 'as1r3', 'as1r6', 'dead:beef::'],
    ['as1r3', 'as1r6', 'dead:beef::'],
    ['as1r4', 'as1r2' ,'as1r3', 'as1r6', 'dead:beef::'],
    ['as1r5', 'as1r6', 'dead:beef::'],
    ['as1r6', 'dead:beef::']
]


@require_root
def test_bgp_full_config():
    try:
        net = IPNet(topo=BGPTopoFull())
        net.start()
        for path in full_paths:
            assert_path_bgp(net, path, config_ip2)
        net.stop()
    finally:
        cleanup()


def assert_path_bgp(net, expected_path, nodes_ips, timeout=300, udp=True):
    src = expected_path[0]
    dst = expected_path[-1]
    dst_ip = ip_address(dst)

    path_ips = traceroute(net, src, dst_ip, timeout=timeout, udp=udp)

    print(path_ips)

    path = [src]
    for path_ip in path_ips:
        found = False
        for node in nodes_ips:
            for ip in nodes_ips[node]:
                if path_ip == dst or ip == path_ip:
                    found = True
                    break
            if found:
                path.append(dst) if path_ip == dst else path.append(node)
                break
        assert found, "Traceroute returned the address '%s' " \
                      "that cannot be linked to a node" % path_ip

    print(path)
    print(expected_path)

    assert path == expected_path, "We expected the path from %s to %s to go " \
                                  "through %s but it went through %s" \
                                  % (src, dst, expected_path[1:-1], path[1:-1])

    
