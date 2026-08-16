Dockerizing the Flask app

Build the image:

```bash
docker build -t court-data-fetcher:latest .
```

Run with Docker:

```bash
docker run --rm -p 8080:8080 \
  -e DATABASE_HOST=your_db_host \
  -e DATABASE_NAME=your_db \
  -e DATABASE_USER=your_user \
  -e DATABASE_PASSWORD=your_pass \
  -e FLASK_SECRET='replace_me' \
  court-data-fetcher:latest
```

Run locally with Postgres via docker-compose:

```bash
docker-compose up --build
```

Notes:
- The app reads database credentials from environment variables. Provide a `DATABASE_URL` or the individual vars.
- For production, set `FLASK_ENV=production` and a secure `FLASK_SECRET`.
