import sys
import signal
import socket
import time
from blockchain.node import Node
from blockchain.utils.logger import logger

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info({"message": f"Received signal {signum}, shutting down gracefully"})
    sys.exit(0)

def check_port_available(ip, port):
    """Check if a port is available for binding"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((ip, port))
            return True
    except OSError:
        return False

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run blockchain node.")
    parser.add_argument(
        "--ip",
        required=True,
        type=str,
        help="The node IP address. Use 0.0.0.0 in Docker, and localhost for native.",
    )
    parser.add_argument(
        "--node_port",
        required=True,
        type=int,
        help="The port used for P2P communication between nodes.",
    )
    parser.add_argument(
        "--api_port",
        required=True,
        type=int,
        help="Port on which the Node API runs.",
    )
    parser.add_argument(
        "--key_file",
        required=False,
        type=str,
        default=None,
        help="The path to the key file of the node (optional).",
    )
    parser.add_argument(
        "--p2p_mode",
        required=False,
        type=str,
        choices=["enhanced", "legacy"],
        default="enhanced",
        help="P2P communication mode: 'enhanced' for Bitcoin-style INV/GETDATA, 'legacy' for direct broadcast (default: enhanced).",
    )
    args = parser.parse_args()

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Check port availability before starting
        if not check_port_available(args.ip, args.node_port):
            logger.error({
                "message": f"P2P port {args.node_port} is already in use on {args.ip}",
                "port": args.node_port,
                "ip": args.ip
            })
            print(f"❌ Error: P2P port {args.node_port} is already in use on {args.ip}")
            sys.exit(1)

        if not check_port_available(args.ip, args.api_port):
            logger.error({
                "message": f"API port {args.api_port} is already in use on {args.ip}",
                "port": args.api_port,
                "ip": args.ip
            })
            print(f"❌ Error: API port {args.api_port} is already in use on {args.ip}")
            sys.exit(1)

        logger.info({
            "message": "Starting blockchain node",
            "node_port": args.node_port,
            "api_port": args.api_port,
            "ip": args.ip,
            "key_file": args.key_file,
            "p2p_mode": args.p2p_mode
        })

        # Create and start the node
        node = Node(args.ip, args.node_port, args.key_file)

        # Start P2P communication with specified mode
        logger.info({"message": f"Starting P2P communication in {args.p2p_mode} mode"})
        if args.p2p_mode == "enhanced":
            node.start_p2p(enhanced=True)
            print(f"🚀 Enhanced P2P started with Bitcoin-style INV/GETDATA protocol")
        else:
            node.start_p2p(enhanced=False)
            print(f"🚀 Legacy P2P started with direct broadcast")

        # Start API server (this now runs in a separate thread)
        logger.info({"message": "Starting API server"})
        node.start_node_api(args.api_port)

        # Keep the main thread alive
        logger.info({"message": "Node fully initialized, running..."})
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info({"message": "Node shutdown requested by user"})
            print("\n🛑 Node shutdown requested")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info({"message": "Node shutdown requested by user"})
        print("\n🛑 Node shutdown requested")
        sys.exit(0)
    except OSError as e:
        if "Address already in use" in str(e):
            logger.error({
                "message": "Port conflict detected during startup",
                "error": str(e),
                "node_port": args.node_port,
                "api_port": args.api_port
            })
            print(f"❌ Port conflict: {e}")
            print(f"   P2P Port: {args.node_port}")
            print(f"   API Port: {args.api_port}")
            print("   Try using different ports or stop conflicting processes")
        else:
            logger.error({
                "message": "Network error during startup",
                "error": str(e)
            })
            print(f"❌ Network error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error({
            "message": "Unexpected error during node startup",
            "error": str(e),
            "error_type": type(e).__name__
        })
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
