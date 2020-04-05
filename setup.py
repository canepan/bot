import setuptools

setuptools.setup(
    name='NicolaCanepa_Tools',
    version='0.0.1',
    author='Nicola Canepa',
    author_email='canne74@gmail.com',
    description='Useful tools',
    packages=setuptools.find_packages('src', exclude=['.tox', 'test']),
    package_dir={"": "src"},
    install_requires=['attrs', 'typing'],
#    package_data={'canepa': ['../templates/*', '../static/*', '../static/*/*']},
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    zip_safe=False,
#    python_requires='>=3.6',
#    entry_points={
#        "console_scripts": [
#        ],
#    }
)


