# WhatsApp SDK

OpenPing's client for the WhatsApp Business Platform (Meta Cloud API), in two languages with
the same endpoints and behaviour.

| Folder | Package | Status |
| --- | --- | --- |
| [`python/`](python/) | [`openping-whatsapp`](https://pypi.org/project/openping-whatsapp/) on PyPI | Published |
| [`rust/`](rust/) | `openping-whatsapp` crate | Not published yet |

## Releasing (Python)

1. Bump `version` in `python/pyproject.toml` and push to `main`.
2. Actions → **Release to PyPI & GitHub** → Run workflow. It tests, builds, publishes to PyPI,
   tags `python-vX.Y.Z`, and creates a GitHub release.

## License

Apache-2.0
