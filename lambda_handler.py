from src.monitor import create_monitor


def handler(event, context):
    """AWS Lambda handler: performs a single monitoring cycle."""
    monitor = create_monitor()
    monitor.run_cycle()
    return {"statusCode": 200, "body": "ok"}
