# Voxvey Hermes Plugin Bundle

This workspace contains a local Hermes plugin bundle for Voxvey's authenticated gateway.

## Environment

- `VOXVEY_TOKEN`: preferred bearer token.
- `VOXVEY_API_KEY`: fallback bearer token.
- `VOXVEY_BASE_URL`: optional override, default `https://api.voxvey.com`.

## Plugins

- `plugins/model-providers/voxvey`: model provider profile for OpenAI-compatible LLM routes.
- `plugins/image_gen/voxvey`: image generation backend for `/v1/images/generations`.
- `plugins/video_gen/voxvey`: video generation backend for BytePlus content task routes.
- `plugins/voxvey_auth`: CLI authentication helper for `hermes voxvey`.

Copy or symlink these plugin directories into the corresponding Hermes plugin locations, depending on whether you want bundled or user-level plugins.

## Authentication

The model provider remains API-key compatible, so Hermes can use `VOXVEY_TOKEN`, `VOXVEY_API_KEY`, or a saved Hermes credential-pool entry.

When the `voxvey_auth` plugin is enabled, it adds:

```sh
hermes voxvey login --manual-paste
hermes voxvey login --device
hermes voxvey api-key
hermes voxvey status
```

OAuth login uses OneHelio with the native client ID supplied for Voxvey/OpenClaw and stores the resulting bearer token in Hermes' `voxvey` credential pool.
