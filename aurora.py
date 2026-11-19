"""Amazon Aurora — Serverless v2 + Data API client.

Run against an Aurora PostgreSQL Serverless v2 cluster with the
RDS Data API enabled. No persistent connection, no driver, no pool:
perfect for Lambda functions and short-lived scripts.

Setup:
    1. Create the cluster with --enable-http-endpoint
       (or enable the Data API in the console).
    2. Store the master credentials in Secrets Manager and pass the
       secret ARN below — never hard-code passwords.

    pip install boto3
"""

import json
import os
import time

import boto3
from botocore.exceptions import ClientError


class AuroraClient:
    """Thin wrapper around the RDS Data API for Aurora Serverless."""

    def __init__(self, cluster_arn, secret_arn, database, region="eu-west-1"):
        self.client = boto3.client("rds-data", region_name=region)
        self.cluster_arn = cluster_arn
        self.secret_arn = secret_arn
        self.database = database

    def execute(self, sql, parameters=None):
        """Run one statement. Returns rows as a list of dicts."""
        kwargs = {
            "resourceArn": self.cluster_arn,
            "secretArn": self.secret_arn,
            "database": self.database,
            "sql": sql,
        }
        if parameters:
            kwargs["parameters"] = parameters
        response = self.client.execute_statement(**kwargs)
        return [self._row_to_dict(row, response["columnMetadata"])
                for row in response.get("records", [])]

    def execute_batch(self, sql, parameter_sets):
        """Run the same statement for many parameter sets in one call."""
        response = self.client.batch_execute_statement(
            resourceArn=self.cluster_arn,
            secretArn=self.secret_arn,
            database=self.database,
            sql=sql,
            parameterSets=parameter_sets,
        )
        return response["updateResults"]

    def transaction(self, statements):
        """Run several statements atomically. Rolls back on any failure."""
        txn = self.client.begin_transaction(
            resourceArn=self.cluster_arn, secretArn=self.secret_arn,
            database=self.database,
        )
        txn_id = txn["transactionId"]
        try:
            for sql, params in statements:
                self.client.execute_statement(
                    resourceArn=self.cluster_arn,
                    secretArn=self.secret_arn,
                    database=self.database,
                    sql=sql,
                    parameters=params or [],
                    transactionId=txn_id,
                )
            self.client.commit_transaction(
                resourceArn=self.cluster_arn, secretArn=self.secret_arn,
                transactionId=txn_id,
            )
        except ClientError:
            self.client.rollback_transaction(
                resourceArn=self.cluster_arn, secretArn=self.secret_arn,
                transactionId=txn_id,
            )
            raise

    @staticmethod
    def _row_to_dict(row, metadata):
        """Convert a Data API record into a plain dict."""
        out = {}
        for field_meta, field in zip(metadata, row):
            value = next(iter(field.values()))
            out[field_meta["name"]] = value
        return out


def wait_for_cluster_available(cluster_id, region="eu-west-1", timeout=900):
    """Poll until the cluster reports 'available' (or fail loudly)."""
    rds = boto3.client("rds", region_name=region)
    deadline = time.time() + timeout
    while time.time() < deadline:
        cluster = rds.describe_db_clusters(
            DBClusterIdentifier=cluster_id)["DBClusters"][0]
        status = cluster["Status"]
        print(f"Cluster {cluster_id}: {status}")
        if status == "available":
            return cluster
        if status in ("failed", "incompatible-restore", "incompatible-network"):
            raise RuntimeError(f"Cluster entered bad state: {status}")
        time.sleep(30)
    raise TimeoutError(f"Cluster {cluster_id} not available after {timeout}s")


def clone_cluster_for_dev(source_cluster_id, clone_id, region="eu-west-1"):
    """Copy-on-write clone — a full copy of prod in minutes, near-zero
    extra storage until the data diverges. Ideal for dev/test."""
    rds = boto3.client("rds", region_name=region)
    response = rds.restore_db_cluster_to_point_in_time(
        SourceDBClusterIdentifier=source_cluster_id,
        DBClusterIdentifier=clone_id,
        RestoreType="copy-on-write",
        UseLatestRestorableTime=True,
        Engine="aurora-postgresql",
    )
    return response["DBCluster"]["DBClusterIdentifier"]


if __name__ == "__main__":
    client = AuroraClient(
        cluster_arn=os.environ["AURORA_CLUSTER_ARN"],
        secret_arn=os.environ["AURORA_SECRET_ARN"],
        database=os.environ.get("AURORA_DATABASE", "shop"),
        region=os.environ.get("AWS_REGION", "eu-west-1"),
    )

    # 1. Schema (idempotent)
    client.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id          SERIAL PRIMARY KEY,
            customer_id INT NOT NULL,
            total       NUMERIC(10, 2) NOT NULL,
            status      VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # 2. Batch insert — one round trip for many rows
    client.execute_batch(
        "INSERT INTO orders (customer_id, total, status) "
        "VALUES (:customer_id, :total, :status)",
        [
            [
                {"name": "customer_id", "value": {"longValue": 101}},
                {"name": "total", "value": {"stringValue": "49.99"}},
                {"name": "status", "value": {"stringValue": "PAID"}},
            ],
            [
                {"name": "customer_id", "value": {"longValue": 102}},
                {"name": "total", "value": {"stringValue": "129.50"}},
                {"name": "status", "value": {"stringValue": "PENDING"}},
            ],
        ],
    )

    # 3. Read via the reader endpoint behaviour: the Data API routes
    #    through the cluster endpoint, so keep read-heavy work on a
    #    reader by using a second client pointed at a reader instance.
    pending = client.execute(
        "SELECT id, customer_id, total FROM orders "
        "WHERE status = :status ORDER BY created_at DESC LIMIT 10",
        [{"name": "status", "value": {"stringValue": "PENDING"}}],
    )
    print(json.dumps(pending, indent=2, default=str))

    # 4. Atomic multi-statement transaction (order + audit row)
    client.transaction([
        ("UPDATE orders SET status = 'PAID' WHERE id = :id",
         [{"name": "id", "value": {"longValue": 2}}]),
        ("INSERT INTO orders (customer_id, total, status) "
         "VALUES (:customer_id, :total, :status)",
         [{"name": "customer_id", "value": {"longValue": 102}},
          {"name": "total", "value": {"stringValue": "129.50"}},
          {"name": "status", "value": {"stringValue": "PAID"}}]),
    ])
    print("Transaction committed.")
