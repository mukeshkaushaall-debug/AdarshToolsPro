# ThugTools Cobalt Relay

This optional relay gives the YouTube downloader another cookieless server path when the main Railway IP is blocked.

Use it only for public content you own or are allowed to process.

## Run on a VPS

1. Install Docker and Docker Compose.
2. Edit `docker-compose.yml` and set `API_URL` to the relay's public HTTPS URL.
3. Start the relay:

```sh
docker compose up -d
```

4. Put a reverse proxy such as Nginx or Caddy in front of port `9000`.
5. In the main ThugTools Railway service, set:

```sh
YOUTUBE_FORCE_COOKIELESS=1
COBALT_API_URL=https://your-cobalt-relay.example/
```

For multiple relays, set:

```sh
COBALT_API_URLS=https://relay-1.example/,https://relay-2.example/
```

Then redeploy ThugTools.
