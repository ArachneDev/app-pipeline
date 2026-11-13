# pipeline-sample: the smallest image the shared build can publish. It only
# exercises app-pipeline's own CI; it is not an app and is never deployed.
FROM docker.io/library/busybox:1.37.0-musl@sha256:5624bb6777cf469b1fb50ae3f981b15d2715ee2fffaf20b9998cfb7843726835
ARG VERSION=dev
RUN mkdir /www && printf '%s\n' "$VERSION" > /www/healthz
USER 65534:65534
ENV PORT=3000
EXPOSE 3000
CMD ["sh", "-c", "exec httpd -f -p \"$PORT\" -h /www"]
