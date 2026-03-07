# Vendored dependencies policy

Lampstand can be built in two modes:

1) **Distro mode**: depend on packaged system libraries.
2) **Platform mode**: vendor platform-standard components (TriTRPC, standard storage, etc.) as pinned commits.

This directory exists so platform builds can vendor dependencies without
entangling them with the core source tree.

We should keep each vendored dependency in its own subdirectory and include:
- upstream URL
- pinned commit or tag
- build steps
- license notes
