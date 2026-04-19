#!/usr/bin/env python
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.db import connection

# Supprimer la table si elle existe
with connection.cursor() as cursor:
    cursor.execute("DROP TABLE IF EXISTS audit_logs")
    print("Table audit_logs supprimée avec succès")