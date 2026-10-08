{{- define "lynk.image" -}}
{{- if .image.digest -}}
{{- printf "%s@%s" .image.repository .image.digest -}}
{{- else -}}
{{- printf "%s:%s" .image.repository .tag -}}
{{- end -}}
{{- end -}}
