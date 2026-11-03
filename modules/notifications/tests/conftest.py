# `identity.client` and `projects.client` import each other; loading `projects.client` first is
# the order the app uses, and the only one that resolves.
import scopesteps.projects.client  # noqa: F401  # pyright: ignore[reportUnusedImport]
