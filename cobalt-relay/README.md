# ThugTools Cobalt Relay

This relay is the production YouTube download provider for ThugTools. The main backend does not use YouTube cookies, manual browser sessions, or scraped public resolver lists; it calls only the Cobalt-compatible relays you configure.

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

For heavy traffic, run relays in separate VPS regions and keep the main backend's `DOWNLOAD_RATE_LIMIT_PER_MINUTE` and `MEDIA_MAX_CONCURRENT_DOWNLOADS` conservative. Failed relays are cooled down automatically by the backend.
