#!/bin/sh
# Run the engine and the control page together; if either stops, stop the container so Docker restarts it.
if [ ! -f /data/devices.json ]; then
  echo "No /data/devices.json. Run the tinytuya wizard first (see the README), e.g.:"
  echo "  docker compose run --rm -it string-theory sh -c 'cd /data && python -m tinytuya wizard'"
  exit 1
fi
if [ ! -f /data/config.json ]; then
  echo "No /data/config.json. Pick your strings first:"
  echo "  docker compose run --rm -it string-theory python configure.py"
  exit 1
fi
python /app/lights.py run & ENGINE=$!
python /app/web.py & WEB=$!
trap 'kill $ENGINE $WEB 2>/dev/null' TERM INT
while kill -0 $ENGINE 2>/dev/null && kill -0 $WEB 2>/dev/null; do sleep 2; done
kill $ENGINE $WEB 2>/dev/null
exit 1
