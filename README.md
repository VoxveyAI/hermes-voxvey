# Voxvey Hermes Plugin Bundle

This package contains Voxvey plugins for Hermes Agent.

## Install

```sh
pip install .
```

After install, Hermes discovers the package through the `hermes_agent.plugins` entry points.

## Environment

- `VOXVEY_TOKEN`: preferred bearer token.
- `VOXVEY_API_KEY`: fallback bearer token.
- `VOXVEY_BASE_URL`: optional override, default `https://api.voxvey.com`.

## Plugins

- `voxvey.model_provider`: model provider profile for OpenAI-compatible LLM routes.
- `voxvey.image_gen`: image generation backend for `/v1/images/generations`.
- `voxvey.video_gen`: video generation backend for `/v1/videos/generations` and `/v1/videos/{id}` polling.
- `voxvey.search`: Firecrawl-compatible web search/extract backend for `/v2/search` and `/v2/scrape`.
- `voxvey.auth_plugin`: CLI authentication helper for `hermes voxvey`.

The `plugins/` directory remains as compatibility wrappers for directory-installed Hermes plugins.

## Authentication

The model provider remains API-key compatible, so Hermes can use `VOXVEY_TOKEN`, `VOXVEY_API_KEY`, or a saved Hermes credential-pool entry.

When the `voxvey_auth` plugin is enabled, it adds:

```sh
hermes voxvey login --manual-paste
hermes voxvey login --device
hermes voxvey api-key
hermes voxvey status
hermes voxvey realtime-secret --model xai/grok-voice-latest
```

OAuth login uses OneHelio with the native client ID supplied for Voxvey/OpenClaw and stores the resulting bearer token in Hermes' `voxvey` credential pool.

A standalone helper is also installed:

```sh
voxvey login --manual-paste
voxvey login --device
voxvey realtime-secret --model xai/grok-voice-latest
voxvey-auth --manual-paste
voxvey-auth --device
```
