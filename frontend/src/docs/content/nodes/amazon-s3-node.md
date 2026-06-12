# Amazon S3 Node

The Amazon S3 node reads and writes objects in [Amazon S3](https://aws.amazon.com/s3/).

## Supported operations

- `Create Bucket`: Creates a bucket in the credential region.
- `Delete Bucket`: Deletes an empty bucket.
- `List Buckets`: Lists buckets visible to the credential.
- `Create Folder`: Creates an empty folder marker (zero-byte key ending with `/`).
- `Delete Folder`: Deletes all objects under a folder prefix (including nested keys).
- `Get All in Folder`: Lists all object metadata under a folder prefix (server-side pagination).
- `Upload Object`: Writes a text payload to a bucket/key.
- `Get Object`: Downloads an object and returns either decoded text or base64 content.
- `Copy Object`: Copies an object to another key or bucket.
- `List Objects`: Lists object metadata under a prefix (single page, up to 1000 keys; supports continuation tokens).
- `Delete Object`: Deletes a single object by key.

## Credential setup

Create an `Amazon S3` credential in the Credentials tab with:

- Access Key ID
- Secret Access Key
- Region
- Optional Session Token (for temporary AWS STS credentials)

## Common fields

- `Bucket`: Target bucket name (destination bucket for copy operations).
- `Object Key`: Path-like object key such as `reports/daily.json`.
- `Folder Path`: Prefix for folder operations (for example `docs/archive`).
- `Source Bucket`: Optional source bucket for copy; defaults to the destination bucket.
- `Source Object Key`: Source key for copy operations.
- `Prefix`: Used by list operations to scope results.
- `Continuation Token`: Optional token from a previous list response to fetch the next page.
- `Max Keys`: Page size for List Objects (1–1000).
- `Include Binary`: When enabled on Get Object, returns `body_base64` instead of `body_text`.
- `Body`: Text content to upload.
- `Content Type`: Optional MIME type for uploaded objects.

## Output examples

### Create Bucket

- `${label}.success`
- `${label}.bucket`
- `${label}.region`

### Delete Bucket

- `${label}.success`
- `${label}.bucket`

### List Buckets

- `${label}.buckets`
- `${label}.count`
- `${label}.buckets[0].name`

### Create Folder

- `${label}.success`
- `${label}.bucket`
- `${label}.folder`
- `${label}.etag`

### Delete Folder

- `${label}.success`
- `${label}.bucket`
- `${label}.folder`
- `${label}.deleted_count`
- `${label}.deleted_keys`

### Get All in Folder

- `${label}.folder`
- `${label}.count`
- `${label}.objects`
- `${label}.objects[0].key`

### Upload Object

- `${label}.success`
- `${label}.bucket`
- `${label}.key`
- `${label}.etag`

### Get Object

- `${label}.content_type`
- `${label}.content_length`
- `${label}.body_text`
- `${label}.body_base64`

### Copy Object

- `${label}.source_bucket`
- `${label}.source_key`
- `${label}.bucket`
- `${label}.key`
- `${label}.etag`

### List Objects

- `${label}.objects`
- `${label}.count`
- `${label}.truncated`
- `${label}.next_continuation_token`
- `${label}.objects[0].key`

### Delete Object

- `${label}.success`
- `${label}.bucket`
- `${label}.key`
- `${label}.delete_marker`

## Notes

- `Upload Object` currently uploads UTF-8 text content.
- `Get Object` can return base64 for binary files by enabling the binary option.
- `Create Bucket` uses the credential region and requires `s3:CreateBucket`.
- `Delete Bucket` requires the bucket to be empty and needs `s3:DeleteBucket`.
- `List Buckets` requires `s3:ListAllMyBuckets`.
- `Create Folder` uploads a zero-byte marker object; S3 has no native directory type.
- `Delete Folder` removes every object whose key starts with the folder prefix; use with care.
- `Get All in Folder` auto-paginates through the prefix until all objects are returned.
- `List Objects` returns one page (up to 1000 keys). When `truncated` is true, pass `next_continuation_token` into the next call's Continuation Token field.
- `Copy Object` requires `s3:GetObject` on the source and `s3:PutObject` on the destination.

## Related

- [Node Types](../reference/node-types.md) – Overview of all node types
- [Credentials](../reference/credentials.md) – Credential types and usage
- [Third-Party Integrations](../reference/integrations.md) – Amazon S3 credential setup
