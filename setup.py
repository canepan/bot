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
    packages=setuptools.find_packages('src', exclude=['.tox', 'test']),
    package_dir={"": "src"},
    data_files=data_files,
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    zip_safe=False,
    python_requires='>=3.9',
)
