# geotriage

A scene-triage engine. Point it at an archive - a public catalogue or your own STAC - define a detector, and it grinds the whole archive so you only open the scenes that matter.

## Running it

```sh
cp .env.example .env    # defaults work as they are
make up                 # start everything
make migrate            # apply database migrations
make llm-pull           # download the workflow builder's model
```

The app is at http://localhost:3000, the API at http://localhost:8000/docs.

`make help` lists every target

## How it works

Three documents cover the design:

- [Architecture](docs/architecture.md) - the services, the job queue, and how a sentence becomes a draft workflow
- [Storage architecture](docs/storage-architecture.md) - the scratch and object stores, storage policies, and the guardrails that stop a run filling the disk
- [AI engineering](docs/ai-engineering.md) - the language model client, prompts, the agent loop, and the eval harness
