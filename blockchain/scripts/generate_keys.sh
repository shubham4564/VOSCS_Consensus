#!/bin/bash

# Generate private/public key pairs for multiple blockchain nodes
# Usage: ./generate_keys.sh [NUMBER_OF_NODES]
# Default: 10 nodes if no parameter provided

# Get number of nodes from command line argument, default to 10
NUM_NODES=${1:-10}

# Validate input
if ! [[ "$NUM_NODES" =~ ^[0-9]+$ ]] || [ "$NUM_NODES" -lt 1 ] || [ "$NUM_NODES" -gt 1000 ]; then
    echo "❌ Error: Please provide a valid number of nodes (1-1000)"
    echo "Usage: $0 [NUMBER_OF_NODES]"
    echo "Example: $0 5    # Generate keys for 5 nodes"
    echo "Example: $0      # Generate keys for 10 nodes (default)"
    exit 1
fi

echo "🔑 Generating key pairs for $NUM_NODES nodes..."

# Create keys directory if it doesn't exist
mkdir -p keys

# Generate genesis keys first if they don't exist
if [ ! -f "keys/genesis_private_key.pem" ]; then
    echo "🔑 Genesis keys not found. Creating genesis key pair..."
    echo -n "   🏛️  Genesis: Generating key pair... "
    
    # Generate ECDSA P-256 private key in PKCS#8 format for genesis
    openssl genpkey -algorithm EC -out "keys/genesis_private_key.pem" -pkeyopt ec_paramgen_curve:P-256 2>/dev/null
    
    if [ $? -eq 0 ]; then
        # Generate public key from private key
        openssl ec -pubout -in "keys/genesis_private_key.pem" -out "keys/genesis_public_key.pem" 2>/dev/null
        
        if [ $? -eq 0 ]; then
            echo "✅ Done"
            echo "   🎉 Genesis keys created successfully!"
        else
            echo "❌ Failed to generate genesis public key"
            rm -f "keys/genesis_private_key.pem"
            exit 1
        fi
    else
        echo "❌ Failed to generate genesis private key"
        exit 1
    fi
else
    echo "🏛️  Genesis keys already exist, skipping..."
fi

# Generate keys for each node (starting from node 2, since node 1 uses genesis)
echo "🚀 Generating node keys..."
generated_count=0
skipped_count=0

for i in $(seq 2 $NUM_NODES); do
    private_key_file="keys/node${i}_private_key.pem"
    public_key_file="keys/node${i}_public_key.pem"
    
    if [ -f "$private_key_file" ]; then
        echo "   📋 Node $i: Keys already exist, skipping"
        ((skipped_count++))
    else
        echo -n "   🔐 Node $i: Generating key pair... "
        
        # Generate ECDSA P-256 private key in PKCS#8 format (replacing RSA)
        openssl genpkey -algorithm EC -out "$private_key_file" -pkeyopt ec_paramgen_curve:P-256 2>/dev/null
        
        if [ $? -eq 0 ]; then
            # Generate public key from private key
            openssl ec -pubout -in "$private_key_file" -out "$public_key_file" 2>/dev/null
            
            if [ $? -eq 0 ]; then
                echo "✅ Done"
                ((generated_count++))
            else
                echo "❌ Failed to generate public key"
                rm -f "$private_key_file"
            fi
        else
            echo "❌ Failed to generate private key"
        fi
    fi
done

echo ""
echo "📊 Key Generation Summary:"
echo "   🔑 Total Nodes: $NUM_NODES"
echo "   🆕 New Keys Generated: $generated_count"
echo "   📋 Existing Keys Skipped: $skipped_count"
echo "   �️  Genesis Key: Created/Verified (Node 1)"

if [ $generated_count -gt 0 ]; then
    echo "   ✅ Key generation completed successfully!"
else
    echo "   📝 All keys already existed, no new keys needed."
fi

echo ""
echo "📁 Key Files Location: keys/"
echo "   🔐 Genesis: keys/genesis_private_key.pem"
echo "   🔐 Staker: keys/staker_private_key.pem (if exists)"
for i in $(seq 2 $NUM_NODES); do
    if [ -f "keys/node${i}_private_key.pem" ]; then
        echo "   🔐 Node $i: keys/node${i}_private_key.pem"
    fi
done

echo ""
echo "💡 Next Steps:"
echo "   🚀 Start nodes: ./start_nodes.sh $NUM_NODES"
echo "   📊 Check status: python3 analyze_forgers.py"
echo "   🧪 Test network: python3 test_transactions.py --count 10"

# Check if we can start nodes now
echo ""
echo "🔍 Checking readiness to start $NUM_NODES nodes..."
ready=true

# Genesis keys should now exist (we create them if missing)
if [ ! -f "keys/genesis_private_key.pem" ]; then
    echo "   ❌ Genesis key creation failed - this shouldn't happen"
    ready=false
fi

missing_keys=0
for i in $(seq 2 $NUM_NODES); do
    if [ ! -f "keys/node${i}_private_key.pem" ] && [ ! -f "keys/staker_private_key.pem" ]; then
        ((missing_keys++))
    fi
done

if [ $missing_keys -gt 0 ] && [ ! -f "keys/staker_private_key.pem" ]; then
    echo "   ⚠️  $missing_keys nodes will use genesis key as fallback"
    echo "   💡 Consider creating staker_private_key.pem for better distribution"
fi

if [ "$ready" = true ]; then
    echo "   ✅ Ready to start $NUM_NODES nodes!"
    echo ""
    read -p "🚀 Start nodes now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🎉 Starting $NUM_NODES nodes..."
        ./start_nodes.sh $NUM_NODES
    fi
else
    echo "   ❌ Not ready to start nodes. Please fix key issues first."
fi
