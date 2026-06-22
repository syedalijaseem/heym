# Heym Postgres image: the official postgres:16 plus the pgvector extension.
#
# We deliberately build FROM postgres:16 (instead of using pgvector/pgvector:pg16)
# so the base image — and therefore the glibc/collation version of the data
# directory — is identical to a plain postgres:16. Swapping an existing
# postgres:16 data dir onto a different-glibc image (pgvector's bookworm build)
# triggers a "collation version mismatch" and risks text/B-tree index corruption.
# Adding the extension on top of the same base avoids that entirely.
FROM postgres:16

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
