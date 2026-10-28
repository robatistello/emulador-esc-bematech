"""Histórico das impressões, guardado em SQLite."""

import json
import sqlite3
from contextlib import closing

PREVIEW_LENGTH = 90
DEFAULT_KEEP = 1000


def job_events(job):
    return [
        {**event, "description": f"Abertura da gaveta {event['drawer']} · pulso de {event['pulse_ms']} ms"}
        for event in job["events"]
        if event["type"] == "drawer"
    ]


def job_summary(job):
    text = " ".join(span["text"] for line in job["lines"] for span in line["spans"])
    preview = text.strip()[:PREVIEW_LENGTH]

    if not preview:
        preview = "; ".join(event["description"] for event in job_events(job))

    return job["created_at"], job["reason"], preview


class History:
    def __init__(self, path, keep=DEFAULT_KEEP):
        self.path = str(path)
        self.keep = keep
        path.parent.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            # O resumo em colunas evita decodificar todos os payloads a cada atualização da lista.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, payload TEXT NOT NULL,"
                " created_at TEXT NOT NULL, reason TEXT NOT NULL, preview TEXT NOT NULL)"
            )

            # Com a tabela já criada, um banco somente leitura abre sem erro e só
            # falharia ao gravar a primeira impressão, depois que ela foi recebida.
            # Um comando de escrita que não afeta linhas já revela isso.
            connection.execute("DELETE FROM jobs WHERE 0")
            self.prune(connection)

    def save(self, job):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO jobs(payload, created_at, reason, preview) VALUES (?, ?, ?, ?)",
                (json.dumps(job), *job_summary(job)),
            )
            self.prune(connection)

    def prune(self, connection):
        if not self.keep:
            return

        # O arquivo não encolhe, mas o SQLite reaproveita o espaço das impressões
        # apagadas nas seguintes, e o tamanho se estabiliza no limite.
        connection.execute(
            "DELETE FROM jobs WHERE id < (SELECT id FROM jobs ORDER BY id DESC LIMIT 1 OFFSET ?)", (self.keep - 1,)
        )

    def clear(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute("DELETE FROM jobs").rowcount

    def version(self):
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT id, created_at FROM jobs ORDER BY id DESC LIMIT 1").fetchone()

        if not row:
            return '"empty"'

        # A numeração recomeça depois de limpar o histórico; a data da última
        # impressão distingue a lista nova de uma antiga com o mesmo número.
        job_id, created_at = row
        return f'"{job_id}-{created_at}"'

    def list(self):
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute("SELECT id, created_at, reason, preview FROM jobs ORDER BY id DESC").fetchall()

        return [
            {"id": job_id, "created_at": created_at, "reason": reason, "preview": preview}
            for job_id, created_at, reason, preview in rows
        ]

    def get(self, job_id):
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()

        if not row:
            return None

        job = json.loads(row[0])
        job["events"] = job_events(job)
        return {"id": job_id, **job}
