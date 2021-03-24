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
    version='0.0.4',
    author='Nicola Canepa',
    author_email='canne74@gmail.com',
    description='Useful tools',
    packages=setuptools.find_packages('src', exclude=['.tox', 'test']),
    package_dir={"": "src"},
    data_files=data_files,
    install_requires=['attrs', 'python-ldap', 'typing', 'ConfigArgParse'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    zip_safe=False,
    python_requires='>=3.6',
    entry_points={
        "console_scripts": [
            "config_e2g = tools.bin.config_proxy:main", # compat
            "config_proxy = tools.bin.config_proxy:main",
            "freedns.py = tools.bin.freedns:main",
            "ldap_browse = tools.bin.ldap_browser:main",
            "sdiff.py = tools.bin.sdiff:main",
            "slapd_log = tools.bin.slapd_log:main",
            "ssync.py = tools.bin.ssync:main",
            "total_block = tools.bin.total_block:main",
        ],
    }
)


