# pipeline-sample

A test image for app-pipeline's own CI. It is not an app and is never deployed.

## Port

Listens on `PORT`, default 3000. `GET /healthz` returns the build version.

## Volumes

None. It writes nothing.

## Dependencies

None.

## Memory

Not measured; busybox `httpd` uses a few MB.
