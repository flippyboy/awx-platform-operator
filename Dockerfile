# ansible-operator v1.42.3 is the newest upstream release, and its binary was
# built with Go 1.26.3 and modules that have known CVEs. Rebuild the same tag
# with a current Go toolchain and patched x/net, x/text, and grpc. Drop this
# stage once an upstream release ships those versions.
FROM golang:1.27.2 AS ansible-operator

ARG ANSIBLE_OPERATOR_VERSION=v1.42.3
WORKDIR /src
RUN git clone --depth 1 --branch "${ANSIBLE_OPERATOR_VERSION}" \
      https://github.com/operator-framework/ansible-operator-plugins.git . \
 && go get \
      golang.org/x/net@v0.60.0 \
      golang.org/x/text@v0.42.0 \
      google.golang.org/grpc@v1.83.2 \
 && go mod tidy \
 && REPO="$(go list -m)" \
 && CGO_ENABLED=0 go build -trimpath -ldflags "\
      -X '${REPO}/internal/version.Version=${ANSIBLE_OPERATOR_VERSION}' \
      -X '${REPO}/internal/version.GitVersion=${ANSIBLE_OPERATOR_VERSION}' \
      -X '${REPO}/internal/version.GitCommit=$(git rev-parse HEAD)' \
      -X '${REPO}/internal/version.KubernetesVersion=v1.32.0' \
      -X '${REPO}/internal/version.ImageVersion=${ANSIBLE_OPERATOR_VERSION}'" \
      -o /ansible-operator ./cmd/ansible-operator

FROM quay.io/operator-framework/ansible-operator:v1.42.3

USER root
RUN microdnf update -y && \
    microdnf install -y openssl

COPY --from=ansible-operator /ansible-operator /usr/local/bin/ansible-operator

# Python packages in the base image with fixed CVEs. The base has no pip, so
# install it for this step only. oauthlib stays on 3.x (requests-oauthlib).
COPY hack/image/requirements-security.txt /tmp/requirements-security.txt
RUN microdnf install -y python3.12-pip && \
    python3 -m pip install --no-cache-dir --disable-pip-version-check \
      --no-deps -r /tmp/requirements-security.txt && \
    python3 -m pip check && \
    microdnf remove -y python3.12-pip && \
    microdnf clean all && \
    rm /tmp/requirements-security.txt

USER 1001

ARG DEFAULT_AWX_VERSION
ARG OPERATOR_VERSION
ENV DEFAULT_AWX_VERSION=${DEFAULT_AWX_VERSION}
ENV OPERATOR_VERSION=${OPERATOR_VERSION}

COPY requirements.yml ${HOME}/requirements.yml
RUN ansible-galaxy collection install -r ${HOME}/requirements.yml \
 && chmod -R ug+rwx ${HOME}/.ansible

COPY watches.yaml ${HOME}/watches.yaml
COPY roles/ ${HOME}/roles/
COPY playbooks/ ${HOME}/playbooks/

ENTRYPOINT ["/tini", "--", "/usr/local/bin/ansible-operator", "run", \
    "--watches-file=./watches.yaml", \
    "--reconcile-period=0s" \
    ]
