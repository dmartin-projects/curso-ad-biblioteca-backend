# core/management/commands/configurar_bucket.py
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "Crea el bucket de media si no existe y le aplica las reglas de CORS y de caducidad (idempotente)."

    def handle(self, *args, **opciones):
        o = settings.STORAGES["default"]["OPTIONS"]
        s3 = boto3.client(
            "s3",
            endpoint_url=o["endpoint_url"],
            aws_access_key_id=o["access_key"],
            aws_secret_access_key=o["secret_key"],
            region_name=o.get("region_name", "us-east-1"),
        )
        bucket = o["bucket_name"]

        try:
            # funciona aunque la clave solo tenga permiso sobre este bucket (R2)
            s3.head_bucket(Bucket=bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
                raise  # 403: la clave no vale o no tiene permiso; no lo tapes creando nada
            s3.create_bucket(Bucket=bucket)
            self.stdout.write(f"Bucket {bucket} creado")

        s3.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": settings.CORS_MEDIA_ORIGENES,  # ["https://gastos.example.com"], nunca "*"
                        # PUT solo si el navegador sube directo
                        "AllowedMethods": ["GET", "HEAD", "PUT"],
                        "AllowedHeaders": ["Content-Type"],
                        "ExposeHeaders": ["ETag", "Content-Disposition"],
                        "MaxAgeSeconds": 3600,  # el navegador cachea la respuesta OPTIONS una hora
                    }
                ]
            },
        )

        s3.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "borrar-temporales",
                        # subidas a medias, exportaciones de un solo uso
                        "Filter": {"Prefix": "tmp/"},
                        "Status": "Enabled",
                        "Expiration": {"Days": 1},
                    },
                    {
                        "ID": "informes-a-los-2-anios",
                        "Filter": {"Prefix": "informes/"},
                        "Status": "Enabled",
                        "Expiration": {"Days": 730},
                    },
                    {
                        "ID": "multipart-abandonados",
                        "Filter": {"Prefix": ""},
                        "Status": "Enabled",
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                    },
                ]
            },
        )
        reglas = s3.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
        cors = s3.get_bucket_cors(Bucket=bucket)["CORSRules"]
        self.stdout.write(
            self.style.SUCCESS(
                f"{bucket}: {len(cors)} regla CORS, {len(reglas)} reglas de caducidad"
            )
        )
