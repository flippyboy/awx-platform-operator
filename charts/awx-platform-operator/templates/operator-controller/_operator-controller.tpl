{{/*
Operator controller Deployment for the platform fork.
Image defaults come from .Values.operator (local monorepo image).
*/}}
{{- define "awx-operator.controller" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    control-plane: controller-manager
    helm.sh/chart: {{ .Chart.Name }}
    app.kubernetes.io/name: awx-platform-operator
  name: awx-operator-controller-manager
spec:
  replicas: 1
  selector:
    matchLabels:
      control-plane: controller-manager
      helm.sh/chart: {{ .Chart.Name }}
  template:
    metadata:
      annotations:
        kubectl.kubernetes.io/default-container: awx-manager
      labels:
        control-plane: controller-manager
        helm.sh/chart: {{ .Chart.Name }}
        app.kubernetes.io/name: awx-platform-operator
    spec:
      containers:
        - args:
            - --secure-listen-address=0.0.0.0:8443
            - --upstream=http://127.0.0.1:8080/
            - --logtostderr=true
            - --v=0
          image: {{ .Values.operator.kubeRbacProxyImage | default "quay.io/brancz/kube-rbac-proxy:v0.15.0" }}
          name: kube-rbac-proxy
          ports:
            - containerPort: 8443
              name: https
              protocol: TCP
          resources:
            limits:
              cpu: 500m
              memory: 128Mi
            requests:
              cpu: 5m
              memory: 64Mi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
        - args:
            - --health-probe-bind-address=:6789
            - --metrics-bind-address=127.0.0.1:8080
            - --leader-elect
            - --leader-election-id=awx-operator
          env:
            - name: ANSIBLE_GATHERING
              value: explicit
            - name: ANSIBLE_DEBUG_LOGS
              value: {{ .Values.operator.ansibleDebugLogs | default "false" | quote }}
            - name: WATCH_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          image: "{{ .Values.operator.image }}:{{ .Values.operator.tag }}"
          imagePullPolicy: {{ .Values.operator.imagePullPolicy | default "IfNotPresent" }}
          livenessProbe:
            httpGet:
              path: /healthz
              port: 6789
            initialDelaySeconds: 15
            periodSeconds: 20
          name: awx-manager
          readinessProbe:
            httpGet:
              path: /readyz
              port: 6789
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            limits:
              cpu: 1500m
              memory: 960Mi
            requests:
              cpu: 50m
              memory: 32Mi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
      {{- with .Values.operator.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      securityContext:
        runAsNonRoot: true
      serviceAccountName: awx-operator-controller-manager
      terminationGracePeriodSeconds: 10
{{- end -}}
