# run livekit server use this command
--  livekit-server --config ./app/voice/livekit/livekit.yaml

# run livekit  sip services use this command
--  sip --config ./app/voice/sip/config.yaml

# run livekit agent use this command
-- python -m app.voice.livekit.server dev

# show all sip outbound list use this command
-- lk sip outbound list

# create a new sip outbound trunk use this command

lk sip outbound create \
  --name vobiz-outbound-new \
  --address cacaf611.sip.vobiz.ai \
  --transport UDP \
  --numbers +918065354620 \
  --auth-username "<CURRENT_USERNAME>" \
  --auth-password "<CURRENT_PASSWORD>" \
  --destination-country IN