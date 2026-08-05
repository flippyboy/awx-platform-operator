{{/*
Generate the name of the postgres secret, expects AWX context passed in
*/}}
{{- define "postgres.secretName" -}}
{{ default (printf "%s-postgres-configuration" .Values.AWX.name) .Values.AWX.postgres.secretName }}
{{- end }}

{{/*
Shared external Postgres secret (platform mode)
*/}}
{{- define "platform.postgresSecretName" -}}
{{- if .Values.externalPostgres.secretName }}
{{- .Values.externalPostgres.secretName }}
{{- else }}
{{- printf "%s-postgres-configuration" .Release.Name }}
{{- end }}
{{- end }}

{{/*
Shared external Redis secret (gateway)
*/}}
{{- define "platform.redisSecretName" -}}
{{- if .Values.externalRedis.secretName }}
{{- .Values.externalRedis.secretName }}
{{- else }}
{{- printf "%s-redis-configuration" .Release.Name }}
{{- end }}
{{- end }}

{{/*
Chart name helper
*/}}
{{- define "awx-platform-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "awx-platform-operator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "awx-platform-operator.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
