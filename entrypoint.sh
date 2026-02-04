#!/bin/sh
set -e

# Build command arguments from environment variables
ARGS=""

# Add arguments from environment variables
[ -n "$NETUID" ] && ARGS="$ARGS --netuid $NETUID"
[ -n "$SUBTENSOR_NETWORK" ] && ARGS="$ARGS --subtensor.network $SUBTENSOR_NETWORK"
[ -n "$WALLET_NAME" ] && ARGS="$ARGS --wallet.name $WALLET_NAME"
[ -n "$WALLET_HOTKEY" ] && ARGS="$ARGS --wallet.hotkey $WALLET_HOTKEY"
[ -n "$LOGGING_LEVEL" ] && ARGS="$ARGS --logging.$LOGGING_LEVEL"
[ -n "$AXON_PORT" ] && ARGS="$ARGS --axon.port $AXON_PORT"
[ -n "$SUBTENSOR_CHAIN_ENDPOINT" ] && ARGS="$ARGS --subtensor.chain_endpoint $SUBTENSOR_CHAIN_ENDPOINT"

# Execute with env var args and any additional args from CMD/docker run
eval "exec python -m neurons.validator $ARGS \"\$@\""

