from setuptools import setup, Extension

module = Extension("matcher",
    sources=["matcher.cpp"],
    extra_compile_args=["/std:c++17", "/Oxb2"],
    #~ extra_compile_args=["/std:c++17", "/Od", "/Zi"],
    #~ extra_link_args=["/DEBUG"]
    )

setup(
    name="matcher",
    version="1.0",
    description="A Matcher module for finding matches in byte sequences",
    ext_modules=[module]
)
