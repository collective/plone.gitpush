from setuptools import setup, find_packages

version = '1.0'

setup(name='plone.git',
      version=version,
      description="",
      long_description=open("README.rst").read() + "\n" +
                       open("CHANGES.txt").read(),
      classifiers=[
        "Framework :: Plone",
        "Programming Language :: Python",
        ],
      keywords='',
      author='Dylan Jay, Plone Foundation',
      author_email='software@pretagov.com',
      url='',
      license='GPL',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['plone'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          'plone.resource',
          'dulwich'
      ],
      extras_require = {
          'test': ['plone.app.testing']
      },
      entry_points="""
      [z3c.autoinclude.plugin]
      target = plone
      """,
      )
