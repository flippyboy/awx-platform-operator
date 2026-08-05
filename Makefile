# awx-platform-operator
.PHONY: help lint helm-sync chart-package kind-up kind-test

help:
	@echo "Targets:"
	@echo "  lint            helm lint + basic checks"
	@echo "  helm-sync       sync CRDs into chart"
	@echo "  chart-package   helm package → dist/"
	@echo "  kind-up         create kind cluster (hack/scripts)"
	@echo "  kind-test       run kind smoke tests"

lint:
	helm lint charts/awx-platform-operator
	helm template test charts/awx-platform-operator \
	  -f charts/awx-platform-operator/examples/platform-kind.yaml >/dev/null

helm-sync:
	./hack/scripts/helm-sync-crds.sh

chart-package: helm-sync
	mkdir -p dist
	helm package charts/awx-platform-operator -d dist

kind-up:
	./hack/scripts/kind-up.sh

kind-test:
	./hack/scripts/kind-test.sh
