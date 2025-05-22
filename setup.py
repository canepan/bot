import os
import setuptools


# Declare your non-python data files:
# Files underneath shell/ will be copied into the build preserving the
# subdirectory structure if they exist.
data_files = []
for root, dirs, files in os.walk('shell'):
    data_files.append((os.path.relpath(root, 'shell'),
                       [os.path.join(root, f) for f in files]))

setuptools.setup(
    name='NicolaCanepa_Tools',
    version='0.1.2',
    author='Nicola Canepa',
    author_email='canne74@gmail.com',
    description='Useful tools',
    packages=setuptools.find_packages('src', exclude=['.tox', 'test']),
    package_dir={"": "src"},
    data_files=data_files,
    install_requires=[
        'attrs',
        'click',
        'click-loglevel',
        'dnspython',
        'eyed3',
        'netifaces-plus',
        'ping3',
        'requests',
        'typing;python_version<"3.7"',
        'ConfigArgParse'
    ],
    extras_requires={
        'ldap': 'python-ldap',
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    zip_safe=False,
    python_requires='>=3.8',
    entry_points={
        "console_scripts": [
            "all.py = tools.bin.all:main",
            "arp-map = tools.bin.arp_map:main",
            "cloudflare_dns.py = tools.bin.cloudflare_dns:main",
            "compare-ka = tools.bin.compare_ka:main",
            "config_e2g = tools.bin.config_proxy:main",  # compat
            "config_proxy = tools.bin.config_proxy:main",
            "freedns.py = tools.bin.freedns:main",
            "html-series = tools.bin.html_series:main",
            "id3-checker = tools.bin.id3checker:cli",
            "ldap_browse = tools.bin.ldap_browser:main [ldap]",
            "openvpn-log = tools.bin.openvpn_log:main",
            "qsm = tools.bin.quick_service_map:main",
            "remote_diff.py = tools.bin.remote_diff:main",
            "sdiff.py = tools.bin.sdiff:main",
            "sservice = tools.bin.service:main",
            "service-map = tools.bin.simple_service_map:main",
            "slapd_log = tools.bin.slapd_log:main",
            "ssync.py = tools.bin.ssync:main",
            "total_block = tools.bin.total_block:main",
            "xymon-speedtest = tools.bin.xymon_speedtest:main",
        ],
    }
)
