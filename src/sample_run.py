from src.monitor import create_monitor

if __name__ == "__main__":
    monitor = create_monitor()
    monitor.run_cycle()
