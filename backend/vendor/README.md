# Vendored contract

`geotriage-sdk` is a separate repo, but the platform imports it,
the admission gate runs its `check_descriptor`, staging runs its `calibrate`, and  the runners build its `Bands`.
Rather than make a build here depend on a registry or a sibling checkout, the built wheel is committed.

A fresh clone of this repo builds with no network and nothing else present.

This is the *contract*, not the catalogue.
Adding a model or a provider is a container image registered through the API and never touches this directory.
Refresh it only when the contract itself changes.

|            |                                                                    |
| ---------- | ------------------------------------------------------------------ |
| wheel      | `geotriage_sdk-0.1.0-py3-none-any.whl`                             |
| sha256     | `eed506c5126b7d9052385e7d54908b54fa67af8fb4070252bdb21583208b52d9` |
| built from | `7c571399977d8f81681aefbe2407424006643203`                         |

## Refreshing it

From the platform repo, with a checkout of the contract next to it:

```bash
make vendor-sdk    # rebuilds the wheel and this file
make build         # rebuild the images against it
```

Commit both files together.
