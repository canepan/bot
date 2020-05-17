import setuptools

setuptools.setup(
    name='NicolaCanepa_Tools',
    version='0.0.2',
    author='Nicola Canepa',
    author_email='canne74@gmail.com',
    description='Useful tools',
    packages=setuptools.find_packages('src', exclude=['.tox', 'test']),
    package_dir={"": "src"},
    install_requires=['attrs', 'typing', 'ConfigArgParse'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    zip_safe=False,
    python_requires='>=3.6',
    entry_points={
        "console_scripts": [
            "config_e2g = tools.bin.config_e2g:main",
            "ldap_browse = tools.bin.ldap_browser:main",
            "sdiff.py = tools.bin.sdiff:main",
            "slapd_log = tools.bin.slapd_log:main",
            "ssync.py = tools.bin.ssync:main",
        ],
    }
)


