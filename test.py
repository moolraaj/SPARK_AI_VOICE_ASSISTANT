#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <math.h>
#include "esp_wifi.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

// ============================================================
// COEXISTENCE CHECK
// ============================================================
#if __has_include("esp_coexist.h")
#include "esp_coexist.h"
#define HAVE_COEX 1
#else
#define HAVE_COEX 0
#endif

// ============================================================
// BLUETOOTH CLASSIC HFP
// ============================================================
#include "esp32-hal-alloc-bt-classic-mem.h"
#include "esp32-hal-bt.h"
#include "esp_bt.h"
#include "esp_bt_device.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp_hf_client_api.h"

// ---- Tuning switches -----------------------------------------------------
#define WIFI_PS_MODE_USED   WIFI_PS_NONE
#define COEX_PREFER_BT      1
// -------------------------------------------------------------------------

// ============================================================
// WIFI
// ============================================================
const char* WIFI_SSID     = "Spark Web";
const char* WIFI_PASSWORD = "Ghumali@995";

// ============================================================
// BACKEND
// ============================================================
const char*    BACKEND_HOST      = "192.168.29.24";
const uint16_t BACKEND_PORT      = 8000;
const char*    BACKEND_BASE_PATH = "/api/v1/ws/voice/";

const unsigned long BACKEND_BOOT_WAIT_MS = 15000;

WebSocketsClient webSocket;

// ============================================================
// DEVICE
// ============================================================
const char* DEVICE_NAME = "SPARK-VOICE-DEVICE";
char deviceId[32];

// ============================================================
// BACKEND / WEBSOCKET STATE
// ============================================================
bool backendInitialized = false;
bool backendConnected   = false;

bool wsBeginInProgress  = false;
bool wsReconnectPending = false;

uint32_t wsDisconnectCount = 0;
uint32_t wsConnectCount    = 0;
uint32_t wsGeneration      = 0;

unsigned long lastWsConnectAttempt = 0;
unsigned long lastWsDisconnect     = 0;

const unsigned long WS_RECONNECT_GUARD = 3000;

// ============================================================
// WIFI STATE
// ============================================================
bool wifiWasConnected = false;
unsigned long lastWifiReconnectAttempt = 0;
const unsigned long WIFI_RECONNECT_INTERVAL = 5000;

// ============================================================
// HFP STATE
// ============================================================
bool hfpReady          = false;
bool hfpConnected      = false;
bool slcConnected      = false;
bool audioConnecting   = false;
bool audioConnected    = false;
bool callIncoming      = false;
bool callActive        = false;
bool remoteDeviceKnown = false;
esp_bd_addr_t remoteDevice = {0};

char callerPhoneNumber[32] = {0};

// ============================================================
// AUTO ANSWER
// ============================================================
bool autoAnswerPending = false;
bool callAnswered      = false;
unsigned long incomingCallTime = 0;
const unsigned long AUTO_ANSWER_DELAY = 4000;

// ============================================================
// HFP TIMERS
// ============================================================
unsigned long lastHfpConnectAttempt   = 0;
unsigned long lastAudioConnectAttempt = 0;
const unsigned long HFP_RECONNECT_INTERVAL   = 5000;
const unsigned long AUDIO_RECONNECT_INTERVAL = 3000;

// ============================================================
// RINGS
// ============================================================
#define AUDIO_RING_SIZE_HEAP    6144
#define AUDIO_RING_SIZE_PSRAM   16384
#define TX_RING_SIZE_HEAP       12288
#define TX_RING_SIZE_PSRAM      16384

#define AUDIO_SEND_CHUNK  960
#define AUDIO_SEND_MIN    480
#define TX_PREBUFFER_MS   120

uint8_t*  audioRing     = nullptr;
uint32_t  audioRingSize = AUDIO_RING_SIZE_HEAP;
uint8_t*  txRing        = nullptr;
uint32_t  txRingSize    = TX_RING_SIZE_HEAP;

volatile uint32_t ringHead = 0;
volatile uint32_t ringTail = 0;

volatile uint32_t audioCallbackCount = 0;
volatile uint32_t audioRxBytes       = 0;
volatile uint32_t audioDroppedBytes  = 0;
uint32_t audioSentBytes  = 0;
uint32_t audioSentFrames = 0;

volatile uint32_t lastCbMs     = 0;
volatile uint32_t maxCbGapMs   = 0;
volatile uint32_t bigGapCount  = 0;
volatile uint32_t maxLoopMs    = 0;

volatile bool pendingCallStarted  = false;
volatile bool pendingCallEnded    = false;
volatile bool pendingAudioFormat  = false;
volatile bool callResumed         = false;
volatile int  audioSampleRate     = 8000;
const char*   audioCodecName      = "CVSD";

volatile uint32_t txRingHead = 0;
volatile uint32_t txRingTail = 0;
portMUX_TYPE txRingMux = portMUX_INITIALIZER_UNLOCKED;
portMUX_TYPE audioRingMux = portMUX_INITIALIZER_UNLOCKED;

volatile bool     txPlaying   = false;
volatile uint32_t txLastRxMs  = 0;

volatile uint32_t txBytesReceived = 0;
volatile uint32_t txBytesSent     = 0;
volatile uint32_t txBytesDropped  = 0;
volatile uint32_t txUnderruns     = 0;

// ============================================================
// AI ACTIVITY TRACKING VARIABLES (NEW - serial monitor logs ke liye)
// ============================================================
// Ye counters AI conversation flow dekhne ke liye hain — serial monitor pe log karenge

// AI_USER_SPEECH_BYTES: Total bytes of user's speech jo AI ko bheje gaye
uint32_t aiUserSpeechBytes = 0;

// AI_USER_SPEECH_CHUNKS: Kitne chunks user speech ke bheje
uint32_t aiUserSpeechChunks = 0;

// AI_RESPONSE_CHUNKS: Kitne chunks AI ne bheje (TTS)
uint32_t aiResponseChunks = 0;

// AI_RESPONSE_BYTES: Total AI TTS bytes receive hue
uint32_t aiResponseBytes = 0;

// AI_TTS_PLAYED_BYTES: Total AI TTS bytes jo phone pe baj gaye
uint32_t aiTtsPlayedBytes = 0;

// AI_LAST_USER_SPEECH_MS: Aakhri baar user speech bhejne ka time
unsigned long aiLastUserSpeechMs = 0;

// AI_LAST_RESPONSE_MS: Aakhri baar AI response aane ka time
unsigned long aiLastResponseMs = 0;

// AI_CONVERSATION_TURN: Conversation turn counter (User<->AI exchanges)
uint32_t aiConversationTurn = 0;

// AI_TTS_START_TIME: Jab TTS playback start hua
unsigned long aiTtsStartTime = 0;

// AI_TTS_STOP_TIME: Jab TTS playback khatam hua
unsigned long aiTtsStopTime = 0;

// AI_TTS_ACTIVE: Kya AI abhi bol raha hai
bool aiTtsActive = false;

// AI_LISTENING: Kya AI user ki awaaz sun raha hai
bool aiListening = false;

// AI_LAST_LOG_MS: Aakhri AI log kab print hua (spam control)
unsigned long aiLastLogMs = 0;

// ============================================================
// FORWARD DECLARATIONS
// ============================================================
void generateDeviceId();
void connectWiFi();
void handleWiFi();
void connectBackend();
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length);
void setupBluetooth();
void connectHFP();
void connectSCO();
void handleAutoAnswer();
void printAddress(const esp_bd_addr_t address);
void saveRemoteDevice(const esp_bd_addr_t address);
void printSystemStatus();
void handleAudioStreaming();
void handlePendingEvents();

// NEW AI log functions
void logAI(const char* emoji, const char* tag, const char* msg);
void logAIStat();
void printAIActivityBanner(const char* title);

void allocRings()
{
  bool ps = psramFound();

  if (ps)
  {
    audioRingSize = AUDIO_RING_SIZE_PSRAM;
    txRingSize    = TX_RING_SIZE_PSRAM;
    audioRing = (uint8_t*)heap_caps_malloc(audioRingSize, MALLOC_CAP_SPIRAM);
    txRing    = (uint8_t*)heap_caps_malloc(txRingSize,    MALLOC_CAP_SPIRAM);
  }

  if (!audioRing)
  {
    audioRingSize = AUDIO_RING_SIZE_HEAP;
    audioRing = (uint8_t*)malloc(audioRingSize);
  }
  if (!txRing)
  {
    txRingSize = TX_RING_SIZE_HEAP;
    txRing = (uint8_t*)malloc(txRingSize);
  }

  Serial.printf("PSRAM: %s | audioRing=%u txRing=%u | %s\n",
                ps ? "YES" : "NO",
                (unsigned)audioRingSize, (unsigned)txRingSize,
                (audioRing && txRing) ? "alloc OK" : "ALLOC FAILED");
}

// ============================================================
// AI ACTIVITY LOG HELPERS (NEW)
// ============================================================
// logAI(): Ek single AI activity line serial monitor pe print karta hai
// Format: [timestamp] <emoji> [TAG] message
void logAI(const char* emoji, const char* tag, const char* msg)
{
  Serial.printf("[%8lus] %s [%s] %s\n",
                millis() / 1000, emoji, tag, msg);
}

// printAIActivityBanner(): Bade AI events ke liye banner print karta hai
void printAIActivityBanner(const char* title)
{
  Serial.println();
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.printf ("║  🤖 AI: %-33s║\n", title);
  Serial.println("╚════════════════════════════════════════════╝");
}

// logAIStat(): Periodic AI stats print karta hai (har 20 sec)
void logAIStat()
{
  Serial.println();
  Serial.println("┌─────────── 🤖 AI ACTIVITY STATS ───────────┐");
  Serial.printf ("│ User speech   : %6lu bytes / %4lu chunks │\n",
                 (unsigned long)aiUserSpeechBytes,
                 (unsigned long)aiUserSpeechChunks);
  Serial.printf ("│ AI response   : %6lu bytes / %4lu chunks │\n",
                 (unsigned long)aiResponseBytes,
                 (unsigned long)aiResponseChunks);
  Serial.printf ("│ TTS played    : %6lu bytes               │\n",
                 (unsigned long)aiTtsPlayedBytes);
  Serial.printf ("│ Conversation  : %6lu turns              │\n",
                 (unsigned long)aiConversationTurn);
  Serial.printf ("│ AI speaking   : %-25s│\n",
                 aiTtsActive ? "YES 🔊" : "no");
  Serial.printf ("│ AI listening  : %-25s│\n",
                 aiListening ? "YES 🎤" : "no");
  Serial.println("└────────────────────────────────────────────┘");
  Serial.println();
}

static inline uint32_t txRingAvailableUnsafe()
{
  return (txRingHead + txRingSize - txRingTail) % txRingSize;
}

static inline uint32_t txRingAvailable()
{
  if (!txRing) return 0;
  portENTER_CRITICAL(&txRingMux);
  uint32_t n = txRingAvailableUnsafe();
  portEXIT_CRITICAL(&txRingMux);
  return n;
}

static inline uint32_t txPrebufferBytes()
{
  return (uint32_t)audioSampleRate * 2 * TX_PREBUFFER_MS / 1000;
}

void txRingWrite(const uint8_t* data, uint32_t len)
{
  if (!txRing) return;
  len &= ~1u;
  if (len == 0) return;

  portENTER_CRITICAL(&txRingMux);
  uint32_t freeBytes = txRingSize - 1 - txRingAvailableUnsafe();
  if (len > freeBytes)
  {
    portEXIT_CRITICAL(&txRingMux);
    txBytesDropped += len;
    return;
  }

  uint32_t first = min(len, txRingSize - txRingHead);
  memcpy(txRing + txRingHead, data, first);
  if (len > first) memcpy(txRing, data + first, len - first);
  txRingHead = (txRingHead + len) % txRingSize;
  portEXIT_CRITICAL(&txRingMux);
}

uint32_t txRingRead(uint8_t* out, uint32_t maxLen)
{
  if (!txRing) return 0;
  portENTER_CRITICAL(&txRingMux);
  uint32_t available = txRingAvailableUnsafe();
  uint32_t n = min(maxLen, available) & ~1u;
  if (n)
  {
    uint32_t first = min(n, txRingSize - txRingTail);
    memcpy(out, txRing + txRingTail, first);
    if (n > first) memcpy(out + first, txRing, n - first);
    txRingTail = (txRingTail + n) % txRingSize;
  }
  portEXIT_CRITICAL(&txRingMux);
  return n;
}

void txRingClear()
{
  portENTER_CRITICAL(&txRingMux);
  txRingTail = txRingHead;
  txPlaying  = false;
  portEXIT_CRITICAL(&txRingMux);
}

// ============================================================
// RX RING
// ============================================================
static inline uint32_t ringAvailableUnsafe()
{
  return (ringHead + audioRingSize - ringTail) % audioRingSize;
}

static inline uint32_t ringAvailable()
{
  if (!audioRing) return 0;
  portENTER_CRITICAL(&audioRingMux);
  uint32_t n = ringAvailableUnsafe();
  portEXIT_CRITICAL(&audioRingMux);
  return n;
}

void ringWrite(const uint8_t* data, uint32_t len)
{
  if (!audioRing) return;
  len &= ~1u;
  if (len == 0) return;

  portENTER_CRITICAL(&audioRingMux);
  uint32_t freeBytes = audioRingSize - 1 - ringAvailableUnsafe();
  if (len > freeBytes)
  {
    portEXIT_CRITICAL(&audioRingMux);
    audioDroppedBytes += len;
    return;
  }

  uint32_t first = min(len, audioRingSize - ringHead);
  memcpy(audioRing + ringHead, data, first);
  if (len > first) memcpy(audioRing, data + first, len - first);
  ringHead = (ringHead + len) % audioRingSize;
  portEXIT_CRITICAL(&audioRingMux);
}

uint32_t ringRead(uint8_t* out, uint32_t maxLen)
{
  if (!audioRing) return 0;
  portENTER_CRITICAL(&audioRingMux);
  uint32_t available = ringAvailableUnsafe();
  uint32_t n = min(maxLen, available) & ~1u;
  if (n)
  {
    uint32_t first = min(n, audioRingSize - ringTail);
    memcpy(out, audioRing + ringTail, first);
    if (n > first) memcpy(out + first, audioRing, n - first);
    ringTail = (ringTail + n) % audioRingSize;
  }
  portEXIT_CRITICAL(&audioRingMux);
  return n;
}

void ringClear()
{
  portENTER_CRITICAL(&audioRingMux);
  ringTail = ringHead;
  portEXIT_CRITICAL(&audioRingMux);
}

// ============================================================
// HFP AUDIO DATA CALLBACKS
// ============================================================
void hfpDataCallback(const uint8_t* buf, uint32_t len)
{
  uint32_t now = millis();
  if (lastCbMs != 0)
  {
    uint32_t gap = now - lastCbMs;
    if (gap > maxCbGapMs) maxCbGapMs = gap;
    if (gap > 40) bigGapCount++;
  }
  lastCbMs = now;

  audioCallbackCount++;
  audioRxBytes += len;
  ringWrite(buf, len);

  if (audioConnected && txRingAvailable() > 0)
  {
      esp_hf_client_outgoing_data_ready();
  }
}

uint32_t hfpOutgoingCallback(uint8_t* buf, uint32_t len)
{
  if (buf == nullptr || len == 0)
  {
    return 0;
  }

  uint32_t avail = txRingAvailable();

  // Audio abhi enough buffered nahi hai.
  // HFP ko fake data mat do.
  if (!txPlaying)
  {
    if (avail < txPrebufferBytes())
    {
      return 0;
    }

    txPlaying = true;

    aiTtsActive = true;
    aiTtsStartTime = millis();

    logAI("🔊", "AI-SPEAK",
          "TTS playback STARTED");

    Serial.printf(
      "[TTS PLAY] buffered=%lu required=%lu\n",
      (unsigned long)avail,
      (unsigned long)txPrebufferBytes()
    );
  }

  uint32_t n = txRingRead(buf, len);

  if (n > 0)
  {
    txBytesSent += n;
    aiTtsPlayedBytes += n;
  }
  else
  {
    txUnderruns++;

    Serial.printf(
      "⚠️ [TTS UNDERRUN] requested=%lu available=%lu\n",
      (unsigned long)len,
      (unsigned long)avail
    );

    return 0;
  }

  return n;
}

// ============================================================
// DEVICE ID
// ============================================================
void generateDeviceId()
{
  uint64_t chipId = ESP.getEfuseMac();

  sprintf(deviceId, "SPARK-%04X%08X",
          (uint16_t)(chipId >> 32),
          (uint32_t)chipId);

  Serial.print("Device ID: ");
  Serial.println(deviceId);
}

// ============================================================
// HELPERS
// ============================================================
void printAddress(const esp_bd_addr_t a)
{
  Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X",
                a[0], a[1], a[2], a[3], a[4], a[5]);
}

void saveRemoteDevice(const esp_bd_addr_t address)
{
  memcpy(remoteDevice, address, ESP_BD_ADDR_LEN);
  remoteDeviceKnown = true;
}

void applyWifiPowerSave()
{
  esp_wifi_set_ps(WIFI_PS_MODE_USED);
}

// ============================================================
// WIFI CONNECT
// ============================================================
void connectWiFi()
{
  Serial.println();
  Serial.println("=================================");
  Serial.println("CONNECTING WIFI");
  Serial.println("=================================");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startTime = millis();

  while (WiFi.status() != WL_CONNECTED && millis() - startTime < 15000)
  {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED)
  {
    wifiWasConnected = true;
    applyWifiPowerSave();
    Serial.println("WIFI CONNECTED");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  }
  else
  {
    wifiWasConnected = false;
    Serial.println("WIFI CONNECTION FAILED");
  }
}

// ============================================================
// WIFI RECONNECT
// ============================================================
void handleWiFi()
{
  if (WiFi.status() == WL_CONNECTED)
  {
    if (!wifiWasConnected)
    {
      wifiWasConnected = true;
      applyWifiPowerSave();
      Serial.println();
      Serial.println("WIFI RECONNECTED");
      Serial.print("IP: ");
      Serial.println(WiFi.localIP());
    }
    return;
  }

  if (wifiWasConnected)
  {
    wifiWasConnected = false;
    Serial.println();
    Serial.println("WIFI DISCONNECTED");
  }

  if (millis() - lastWifiReconnectAttempt >= WIFI_RECONNECT_INTERVAL)
  {
    lastWifiReconnectAttempt = millis();

    Serial.println("Trying WiFi reconnect...");

    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

// ============================================================
// BACKEND CONNECT
// ============================================================
void connectBackend()
{
  if (WiFi.status() != WL_CONNECTED)
    return;

  if (backendConnected)
    return;

  if (wsBeginInProgress)
    return;

  unsigned long now = millis();

  if (lastWsConnectAttempt != 0 &&
      now - lastWsConnectAttempt < WS_RECONNECT_GUARD)
  {
    return;
  }

  wsBeginInProgress = true;
  wsReconnectPending = false;
  lastWsConnectAttempt = now;

  Serial.println();
  Serial.println("=================================");
  Serial.println("STARTING BACKEND WEBSOCKET");
  Serial.println("=================================");

  String websocketPath = String(BACKEND_BASE_PATH) + deviceId;

  Serial.print("Host: ");
  Serial.println(BACKEND_HOST);

  Serial.print("Path: ");
  Serial.println(websocketPath);

  Serial.printf("Free heap before WS: %u\n", ESP.getFreeHeap());
  Serial.printf("Next WS generation: %lu\n",
                (unsigned long)wsGeneration + 1);

  webSocket.begin(
      BACKEND_HOST,
      BACKEND_PORT,
      websocketPath.c_str(),
      ""
  );

  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(2000);
  webSocket.enableHeartbeat(30000, 15000, 3);

  backendInitialized = true;
  wsBeginInProgress = false;

  Serial.println("BACKEND WEBSOCKET INITIALIZED");
  Serial.println("Waiting for WS CONNECTED event...");
}

// ============================================================
// WEBSOCKET EVENT
// ============================================================
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length)
{
  switch (type)
  {
    case WStype_CONNECTED:
  {
    backendConnected = true;
    wsBeginInProgress = false;
    wsReconnectPending = false;

    wsConnectCount++;
    wsGeneration++;

    Serial.println();
    printAIActivityBanner("BACKEND CONNECTED");

    Serial.printf("WS connection #%lu\n", (unsigned long)wsConnectCount);
    Serial.printf("WS generation #%lu\n", (unsigned long)wsGeneration);
    Serial.printf("Uptime: %lus\n", millis() / 1000);
    Serial.printf("WiFi RSSI: %d dBm\n", WiFi.RSSI());
    Serial.printf("Free heap: %u\n", ESP.getFreeHeap());

    char msgBuf[96];

    snprintf(
        msgBuf,
        sizeof(msgBuf),
        "{\"event\":\"device_ready\",\"device_id\":\"%s\"}",
        deviceId
    );

    if (webSocket.sendTXT(msgBuf))
    {
      Serial.println("device_ready SENT");
      logAI("📤", "AI-READY", "Sent device_ready to backend (AI is now online)");
    }
    else
    {
      Serial.println("WARNING: device_ready SEND FAILED");
    }

    if (callActive)
    {
      pendingCallStarted = true;
      callResumed = true;
      logAI("🔁", "AI-RESUME", "WS reconnected while call active -> resume pending");
    }

    if (audioConnected)
    {
      pendingAudioFormat = true;
      logAI("🎵", "AI-FORMAT", "WS reconnected while SCO active -> format pending");
    }

    ringClear();
    txRingClear();

    Serial.println("Audio buffers cleared after WS connection");
    break;
  }

  case WStype_DISCONNECTED:
  {
    backendConnected = false;
    wsBeginInProgress = false;

    wsDisconnectCount++;
    lastWsDisconnect = millis();

    wsReconnectPending = true;

    Serial.println();
    printAIActivityBanner("BACKEND DISCONNECTED");

    Serial.printf("Disconnect #%lu\n", (unsigned long)wsDisconnectCount);
    Serial.printf("WS generation: %lu\n", (unsigned long)wsGeneration);
    Serial.printf("Uptime: %lus\n", millis() / 1000);
    Serial.printf("WiFi: %s\n",
                  WiFi.status() == WL_CONNECTED ? "CONNECTED" : "DISCONNECTED");

    if (WiFi.status() == WL_CONNECTED)
    {
      Serial.printf("WiFi RSSI: %d dBm\n", WiFi.RSSI());
    }

    Serial.printf("Free heap: %u\n", ESP.getFreeHeap());
    Serial.printf("Largest block: %u\n",
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    Serial.printf("Min heap: %u\n", ESP.getMinFreeHeap());
    Serial.printf("Call: %s\n", callActive ? "ACTIVE" : "NONE");
    Serial.printf("SCO: %s\n", audioConnected ? "CONNECTED" : "NO");

    Serial.println("WS reconnect requested - library will handle reconnect");
    logAI("⚠️", "AI-OFFLINE", "Backend disconnected - AI unavailable until reconnect");
    break;
  }

  case WStype_ERROR:
  {
    backendConnected = false;
    wsBeginInProgress = false;
    wsReconnectPending = true;

    Serial.println();
    printAIActivityBanner("BACKEND WEBSOCKET ERROR");

    Serial.printf("WS generation: %lu\n", (unsigned long)wsGeneration);
    Serial.printf("WiFi: %s\n",
                  WiFi.status() == WL_CONNECTED ? "CONNECTED" : "DISCONNECTED");
    Serial.printf("Free heap: %u\n", ESP.getFreeHeap());

    if (payload != nullptr && length > 0)
    {
      Serial.print("Error payload: ");
      for (size_t i = 0; i < length; i++)
        Serial.print((char)payload[i]);
      Serial.println();
    }
    logAI("❌", "AI-ERROR", "WebSocket error - will retry automatically");
    break;
  }

    case WStype_TEXT:
    {
      if (payload != nullptr && length > 0)
      {
        const char* p = (const char*)payload;

        // Backend se aaya text message log karo
        Serial.println();
        Serial.printf("📩 [AI-TEXT] Backend says: %s\n", p);

        // Barge-in: backend ne TTS cancel maanga hai
        if (strstr(p, "ai_audio_cancel"))
        {
          txRingClear();
          aiTtsActive = false;
          Serial.println("🛑 [TTS CANCEL] Backend requested audio buffer clear");
          logAI("🛑", "AI-INTERRUPT", "Backend cancelled TTS (user barge-in or new command)");
          break;
        }

        if (strstr(p, "\"error\""))
        {
          logAI("❌", "AI-ERROR", p);
        }
        else if (strstr(p, "call_ready"))
        {
          logAI("✅", "AI-CALL", "Backend call pipeline ready");
        }
        else if (strstr(p, "server_ready"))
        {
          logAI("✅", "AI-SERVER", "Backend server ready");
        }
        else if (strstr(p, "transcript") || strstr(p, "user_said"))
        {
          // Agar backend transcript bheje to usko clearly dikhao
          logAI("📝", "AI-HEARD", p);
        }
        else if (strstr(p, "ai_text") || strstr(p, "response_text"))
        {
          logAI("💬", "AI-SAID", p);
        }
      }
      break;
    }

  case WStype_BIN:
  {
    if (payload != nullptr && length > 0)
    {
      txRingWrite(payload, length);

      txBytesReceived += length;
      txLastRxMs = millis();

      aiResponseBytes += length;
      aiResponseChunks++;
      aiLastResponseMs = millis();

      Serial.printf(
        "📥 [TTS RX] chunk=%u bytes | ring=%u | total=%lu\n",
        (unsigned)length,
        (unsigned)txRingAvailable(),
        (unsigned long)txBytesReceived
      );

      if (aiResponseChunks == 1)
      {
        Serial.println();
        logAI(
          "📥",
          "AI-RESPONSE",
          "Backend TTS PCM received"
        );
      }

      // IMPORTANT:
      // Backend se TTS data aa gaya.
      // HFP lower layer ko immediately data fetch karne bolo.
      if (audioConnected && slcConnected)
      {
        esp_hf_client_outgoing_data_ready();
      }
    }

    static uint32_t binCount = 0;
    binCount++;

    if (binCount % 50 == 0)
    {
      Serial.printf(
        "📦 [AI-TTS] chunk #%lu | ring=%u | received=%lu | played=%lu | drop=%lu | underrun=%lu\n",
        (unsigned long)binCount,
        (unsigned)txRingAvailable(),
        (unsigned long)txBytesReceived,
        (unsigned long)txBytesSent,
        (unsigned long)txBytesDropped,
        (unsigned long)txUnderruns
      );
    }

    break;
  }

    case WStype_PING:
      logAI("🏓", "AI-PING", "Ping sent to backend");
      break;

    case WStype_PONG:
      logAI("🏓", "AI-PONG", "Pong received from backend (connection alive)");
      break;

    default:
      break;
  }
}

// ============================================================
// BLUETOOTH GAP CALLBACK
// ============================================================
void gapCallback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t* param)
{
  switch (event)
  {
    case ESP_BT_GAP_CFM_REQ_EVT:
    {
      Serial.println();
      Serial.println("PAIRING CONFIRMATION");
      Serial.print("Phone: ");
      printAddress(param->cfm_req.bda);
      Serial.println();
      Serial.print("Confirm value: ");
      Serial.println(param->cfm_req.num_val);

      saveRemoteDevice(param->cfm_req.bda);

      esp_err_t result = esp_bt_gap_ssp_confirm_reply(param->cfm_req.bda, true);

      Serial.print("Pairing confirmation: ");
      Serial.println(result == ESP_OK ? "ACCEPTED" : "FAILED");
      logAI("📱", "AI-PAIR", "Phone pairing confirmed (auto-accept)");
      break;
    }

    case ESP_BT_GAP_PIN_REQ_EVT:
    {
      Serial.println();
      Serial.println("PIN REQUEST");
      Serial.print("Phone: ");
      printAddress(param->pin_req.bda);
      Serial.println();

      saveRemoteDevice(param->pin_req.bda);

      esp_bt_pin_code_t pinCode = {'0', '0', '0', '0'};

      esp_err_t result =
        esp_bt_gap_pin_reply(param->pin_req.bda, true, 4, pinCode);

      Serial.print("PIN reply: ");
      Serial.println(result == ESP_OK ? "ACCEPTED" : "FAILED");
      logAI("📱", "AI-PAIR", "Phone PIN accepted (0000)");
      break;
    }

    case ESP_BT_GAP_AUTH_CMPL_EVT:
    {
      Serial.println();
      Serial.println("AUTHENTICATION COMPLETE");
      Serial.print("Phone: ");
      printAddress(param->auth_cmpl.bda);
      Serial.println();

      if (param->auth_cmpl.stat == ESP_BT_STATUS_SUCCESS)
      {
        Serial.println("Authentication SUCCESS");
        saveRemoteDevice(param->auth_cmpl.bda);
        logAI("✅", "AI-PAIR", "Phone authentication SUCCESS");
      }
      else
      {
        Serial.println("Authentication FAILED");
        logAI("❌", "AI-PAIR", "Phone authentication FAILED");
      }
      break;
    }

    default:
      break;
  }
}

// ============================================================
// HFP CALLBACK
// ============================================================
void hfpCallback(esp_hf_client_cb_event_t event, esp_hf_client_cb_param_t* param)
{
  switch (event)
  {
    case ESP_HF_CLIENT_PROF_STATE_EVT:
    {
      Serial.println();
      Serial.println("HFP PROFILE EVENT");

      if (param->prof_stat.state == ESP_HF_INIT_SUCCESS ||
          param->prof_stat.state == ESP_HF_INIT_ALREADY)
      {
        hfpReady = true;
        Serial.println("HFP PROFILE READY");
        logAI("✅", "AI-HFP", "HFP profile ready");
      }
      else
      {
        hfpReady = false;
        Serial.println("HFP PROFILE FAILED");
        logAI("❌", "AI-HFP", "HFP profile FAILED");
      }
      break;
    }

    case ESP_HF_CLIENT_CONNECTION_STATE_EVT:
    {
      esp_hf_client_connection_state_t state = param->conn_stat.state;

      saveRemoteDevice(param->conn_stat.remote_bda);

      Serial.println();
      Serial.println("HFP CONNECTION EVENT");
      Serial.print("Phone: ");
      printAddress(param->conn_stat.remote_bda);
      Serial.println();

      if (state == ESP_HF_CLIENT_CONNECTION_STATE_CONNECTING)
      {
        Serial.println("HFP CONNECTING...");
      }
      else if (state == ESP_HF_CLIENT_CONNECTION_STATE_CONNECTED)
      {
        hfpConnected = true;
        Serial.println("HFP RFCOMM CONNECTED");
        logAI("📞", "AI-HFP", "Phone RFCOMM connected");
      }
      else if (state == ESP_HF_CLIENT_CONNECTION_STATE_SLC_CONNECTED)
      {
        hfpConnected = true;
        slcConnected = true;
        Serial.println("HFP SLC CONNECTED");
        logAI("📞", "AI-HFP", "Phone SLC ready (call control active)");
      }
      else if (state == ESP_HF_CLIENT_CONNECTION_STATE_DISCONNECTED)
      {
        hfpConnected      = false;
        slcConnected      = false;
        audioConnecting   = false;
        audioConnected    = false;
        callIncoming      = false;
        callActive        = false;
        autoAnswerPending = false;
        callAnswered      = false;

        Serial.println("HFP DISCONNECTED");
        logAI("📵", "AI-HFP", "Phone disconnected");
      }
      break;
    }

    case ESP_HF_CLIENT_AUDIO_STATE_EVT:
    {
      esp_hf_client_audio_state_t state = param->audio_stat.state;

      Serial.println();
      Serial.println("HFP AUDIO EVENT");

      if (state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTING)
      {
        audioConnecting = true;
        Serial.println("SCO AUDIO CONNECTING...");
      }
      else if (state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTED)
      {
        audioConnecting = false;
        audioConnected  = true;
        audioSampleRate = 8000;
        audioCodecName  = "CVSD";
        lastCbMs = 0; maxCbGapMs = 0; bigGapCount = 0;
        ringClear();
        txRingClear();
        pendingAudioFormat = true;
        Serial.println("SCO AUDIO CONNECTED | Codec: CVSD | 8000 Hz");
        printAIActivityBanner("VOICE CHANNEL OPEN (CVSD 8kHz)");
        logAI("🎤", "AI-LISTEN", "SCO audio connected - AI can now hear you");
        aiListening = true;
        aiUserSpeechBytes = 0;
        aiUserSpeechChunks = 0;
        aiResponseBytes = 0;
        aiResponseChunks = 0;
      }
      else if (state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTED_MSBC)
      {
        audioConnecting = false;
        audioConnected  = true;
        audioSampleRate = 16000;
        audioCodecName  = "mSBC";
        lastCbMs = 0; maxCbGapMs = 0; bigGapCount = 0;
        ringClear();
        txRingClear();
        pendingAudioFormat = true;
        Serial.println("SCO AUDIO CONNECTED | Codec: mSBC | 16000 Hz");
        printAIActivityBanner("VOICE CHANNEL OPEN (mSBC 16kHz HD)");
        logAI("🎤", "AI-LISTEN", "SCO audio connected - AI can now hear you");
        aiListening = true;
        aiUserSpeechBytes = 0;
        aiUserSpeechChunks = 0;
        aiResponseBytes = 0;
        aiResponseChunks = 0;
      }
      else if (state == ESP_HF_CLIENT_AUDIO_STATE_DISCONNECTED)
      {
        audioConnecting = false;
        audioConnected  = false;
        Serial.println("SCO AUDIO DISCONNECTED");
        logAI("🔇", "AI-LISTEN", "SCO audio disconnected");
        aiListening = false;
      }
      break;
    }

    case ESP_HF_CLIENT_CIND_CALL_SETUP_EVT:
    {
      if (param->call_setup.status == ESP_HF_CALL_SETUP_STATUS_INCOMING)
      {
        callerPhoneNumber[0] = '\0';

        callIncoming      = true;
        callAnswered      = false;
        autoAnswerPending = true;
        incomingCallTime  = millis();

        Serial.println();
        Serial.println("INCOMING CALL");
        Serial.println("Device will answer in 4 seconds...");
        printAIActivityBanner("INCOMING CALL - AI WILL ANSWER IN 4s");
      }
      else
      {
        callIncoming = false;

        if (!callActive)
        {
          autoAnswerPending = false;
          Serial.println("Incoming call cancelled.");
          logAI("❌", "AI-CALL", "Incoming call cancelled");
        }
      }
      break;
    }

    case ESP_HF_CLIENT_CIND_CALL_EVT:
    {
      if (param->call.status == ESP_HF_CALL_STATUS_CALL_IN_PROGRESS)
      {
        callActive         = true;
        autoAnswerPending  = false;
        callAnswered       = true;
        callResumed        = false;
        pendingCallStarted = true;

        if (audioConnected)
        {
          pendingAudioFormat = true;
        }

        Serial.println();
        Serial.println("CALL ACTIVE");
        printAIActivityBanner("CALL ACTIVE - AI IS LIVE");
      }
      else
      {
        bool wasActive = callActive;

        callActive           = false;
        callIncoming         = false;
        autoAnswerPending    = false;
        callAnswered         = false;
        audioConnecting      = false;
        audioConnected       = false;
        callResumed          = false;
        callerPhoneNumber[0] = '\0';

        if (wasActive) pendingCallEnded = true;

        Serial.println();
        Serial.println("CALL ENDED");
        printAIActivityBanner("CALL ENDED - AI SESSION DONE");
        logAI("📴", "AI-CALL", "Call ended - AI session complete");
        aiListening = false;
        aiTtsActive = false;
      }
      break;
    }

    case ESP_HF_CLIENT_RING_IND_EVT:
    {
      callIncoming = true;

      if (!autoAnswerPending && !callActive)
      {
        autoAnswerPending = true;
        callAnswered      = false;
        incomingCallTime  = millis();

        Serial.println();
        Serial.println("PHONE IS RINGING | AUTO ANSWER IN 4 SECONDS");
        logAI("🔔", "AI-RING", "Phone ringing - auto-answer in 4s");
      }
      break;
    }

    case ESP_HF_CLIENT_CLIP_EVT:
    {
      if (param->clip.number != nullptr && strlen(param->clip.number) > 0)
      {
        strncpy(callerPhoneNumber, param->clip.number, sizeof(callerPhoneNumber) - 1);
        callerPhoneNumber[sizeof(callerPhoneNumber) - 1] = '\0';
        Serial.print("CLIP - Caller: ");
        Serial.println(callerPhoneNumber);
        logAI("👤", "AI-CALLER", callerPhoneNumber);
      }
      else
      {
        callerPhoneNumber[0] = '\0';
        Serial.println("CLIP - Caller number hidden/unavailable");
      }
      break;
    }

    default:
      break;
  }
}

// ============================================================
// AUTO ANSWER
// ============================================================
void handleAutoAnswer()
{
  if (!autoAnswerPending) return;

  if (!callIncoming || callActive || callAnswered)
  {
    autoAnswerPending = false;
    return;
  }

  if (millis() - incomingCallTime >= AUTO_ANSWER_DELAY)
  {
    Serial.println();
    Serial.println("AUTO ANSWERING CALL");

    esp_err_t result = esp_hf_client_answer_call();

    Serial.print("Answer command: ");

    if (result == ESP_OK)
    {
      Serial.println("OK");
      callAnswered      = true;
      autoAnswerPending = false;
      logAI("📞", "AI-ANSWER", "Auto-answered call - AI conversation starting");
    }
    else
    {
      Serial.print("FAILED: ");
      Serial.println(result);
      callAnswered = false;
      logAI("❌", "AI-ANSWER", "Auto-answer FAILED");
    }
  }
}

// ============================================================
// CONNECT HFP
// ============================================================
void connectHFP()
{
  if (!hfpReady) return;
  if (!remoteDeviceKnown) return;
  if (slcConnected) return;

  unsigned long now = millis();

  if (now - lastHfpConnectAttempt < HFP_RECONNECT_INTERVAL) return;

  lastHfpConnectAttempt = now;

  Serial.println();
  Serial.println("TRYING HFP CONNECTION");
  Serial.print("Phone: ");
  printAddress(remoteDevice);
  Serial.println();

  esp_err_t result = esp_hf_client_connect(remoteDevice);

  Serial.print("HFP connect request: ");

  if (result == ESP_OK)
  {
    Serial.println("OK");
  }
  else
  {
    Serial.print("FAILED: ");
    Serial.println(result);
  }
}

// ============================================================
// CONNECT SCO
// ============================================================
void connectSCO()
{
  if (!slcConnected) return;
  if (!callActive) return;
  if (audioConnected) return;
  if (audioConnecting) return;
  if (!remoteDeviceKnown) return;

  unsigned long now = millis();

  if (now - lastAudioConnectAttempt < AUDIO_RECONNECT_INTERVAL) return;

  lastAudioConnectAttempt = now;
  audioConnecting = true;

  Serial.println();
  Serial.println("OPENING SCO AUDIO");

  esp_err_t result = esp_hf_client_connect_audio(remoteDevice);

  Serial.print("SCO request: ");

  if (result == ESP_OK)
  {
    Serial.println("OK");
    logAI("🎤", "AI-LISTEN", "Opening SCO audio channel...");
  }
  else
  {
    Serial.print("FAILED: ");
    Serial.println(result);
    audioConnecting = false;
  }
}

// ============================================================
// PENDING EVENTS -> BACKEND
// ============================================================
void handlePendingEvents()
{
  if (!backendConnected) return;

  static char evtBuf[256];

  if (pendingCallStarted)
  {
    pendingCallStarted = false;

    int n = snprintf(evtBuf, sizeof(evtBuf),
                     "{\"event\":\"call_started\",\"device_id\":\"%s\"", deviceId);

    if (strlen(callerPhoneNumber) > 0)
    {
      n += snprintf(evtBuf + n, sizeof(evtBuf) - n,
                    ",\"caller_phone\":\"%s\"", callerPhoneNumber);
    }

    if (callResumed)
    {
      n += snprintf(evtBuf + n, sizeof(evtBuf) - n, ",\"resumed\":true");
      callResumed = false;
    }

    snprintf(evtBuf + n, sizeof(evtBuf) - n, "}");

    webSocket.sendTXT(evtBuf);
    Serial.print("call_started SENT: ");
    Serial.println(evtBuf);
    logAI("📤", "AI-CALL", "Sent call_started to backend");
  }

  if (pendingAudioFormat)
  {
    pendingAudioFormat = false;
    snprintf(evtBuf, sizeof(evtBuf),
             "{\"event\":\"audio_format\",\"codec\":\"%s\",\"sample_rate\":%d,\"bits\":16,\"channels\":1}",
             audioCodecName, audioSampleRate);
    webSocket.sendTXT(evtBuf);
    Serial.print("audio_format SENT: ");
    Serial.println(evtBuf);
    logAI("📤", "AI-FORMAT", "Sent audio_format to backend");
  }

  if (pendingCallEnded)
  {
    pendingCallEnded = false;
    webSocket.sendTXT("{\"event\":\"call_ended\"}");
    Serial.println("call_ended SENT");
    ringClear();
    txRingClear();
    logAI("📤", "AI-CALL", "Sent call_ended to backend");
  }
}

// ============================================================
// AUDIO STREAMING -> BACKEND
// ============================================================
void handleAudioStreaming()
{
  if (!backendConnected || !audioConnected) return;

  static uint8_t chunk[AUDIO_SEND_CHUNK];

  for (int i = 0; i < 2; i++)
  {
    uint32_t avail = ringAvailable() & ~1u;
    if (avail < AUDIO_SEND_MIN) break;

    uint32_t want = avail < AUDIO_SEND_CHUNK ? avail : AUDIO_SEND_CHUNK;
    uint32_t n = ringRead(chunk, want);
    n &= ~1u;
    if (n == 0) break;

    if (webSocket.sendBIN(chunk, n))
    {
      audioSentBytes += n;
      audioSentFrames++;

      // ===== AI LOG: User ki awaaz AI ko bhej rahe hain =====
      aiUserSpeechBytes += n;
      aiUserSpeechChunks++;
      aiLastUserSpeechMs = millis();

      // Pehla chunk aaye to log karo (spam control)
      if (aiUserSpeechChunks == 1)
      {
        Serial.println();
        logAI("🎤", "AI-HEAR", "User is speaking -> streaming to AI...");
      }
    }
    else
    {
      Serial.println("[WS AUDIO] sendBIN failed");
      logAI("❌", "AI-HEAR", "Failed to send user audio to backend");
      break;
    }
    delay(0);
  }
}

// ============================================================
// BLUETOOTH SETUP
// ============================================================
void setupBluetooth()
{
  Serial.println();
  Serial.println("STARTING BLUETOOTH");
  Serial.printf("Free heap before BT: %u\n", ESP.getFreeHeap());

  if (!btStarted())
  {
    Serial.println("Starting Bluetooth controller...");

    if (!btStart())
    {
      Serial.println("Bluetooth controller FAILED");
      return;
    }
  }

  Serial.println("Bluetooth controller started");

  esp_err_t result;

  result = esp_bluedroid_init();

  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE)
  {
    Serial.print("Bluedroid init failed: ");
    Serial.println(result);
    return;
  }

  result = esp_bluedroid_enable();

  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE)
  {
    Serial.print("Bluedroid enable failed: ");
    Serial.println(result);
    return;
  }

  Serial.println("Bluedroid enabled");

  esp_bt_dev_set_device_name(DEVICE_NAME);

  Serial.print("Device name: ");
  Serial.println(DEVICE_NAME);

  result = esp_bt_gap_register_callback(gapCallback);

  if (result != ESP_OK)
  {
    Serial.print("GAP callback failed: ");
    Serial.println(result);
    return;
  }

  result = esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE,
                                    ESP_BT_GENERAL_DISCOVERABLE);

  if (result != ESP_OK)
  {
    Serial.print("Scan mode failed: ");
    Serial.println(result);
  }
  else
  {
    Serial.println("Bluetooth CONNECTABLE + DISCOVERABLE");
  }

  result = esp_hf_client_register_callback(hfpCallback);

  if (result != ESP_OK)
  {
    Serial.print("HFP callback failed: ");
    Serial.println(result);
    return;
  }

  result = esp_hf_client_register_data_callback(hfpDataCallback, hfpOutgoingCallback);

  if (result != ESP_OK)
  {
    Serial.print("HFP data callback failed: ");
    Serial.println(result);
  }
  else
  {
    Serial.println("HFP audio data callback registered");
  }

  result = esp_hf_client_init();

  if (result != ESP_OK)
  {
    Serial.print("HFP init failed: ");
    Serial.println(result);
    return;
  }

  Serial.println("HFP initialization started...");
  Serial.printf("Free heap after BT: %u\n", ESP.getFreeHeap());
}

// ============================================================
// SYSTEM STATUS (20s)
// ============================================================
void printSystemStatus()
{
  static unsigned long lastStatus = 0;
  static uint32_t lastRxBytes = 0;

  unsigned long now = millis();
  if (now - lastStatus < 20000) return;

  unsigned long dt = now - lastStatus;
  lastStatus = now;

  Serial.printf("[STATUS] wifi=%s ws=%s hfp=%s call=%s sco=%s heap=%u minheap=%u rssi=%d\n",
                WiFi.status() == WL_CONNECTED ? "OK" : "NO",
                backendConnected ? "OK" : "NO",
                (slcConnected || hfpConnected) ? "OK" : "NO",
                callActive ? "ACTIVE" : (callIncoming ? "INCOMING" : "NONE"),
                audioConnected ? "OK" : (audioConnecting ? "CONNECTING" : "NO"),
                ESP.getFreeHeap(), ESP.getMinFreeHeap(),
                WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0);

  Serial.printf("[WS] disconnects=%u\n", (unsigned)wsDisconnectCount);

  uint32_t rxNow = audioRxBytes;
  uint32_t rate = (dt > 0) ? (uint32_t)((uint64_t)(rxNow - lastRxBytes) * 1000ULL / dt) : 0;
  lastRxBytes = rxNow;
  uint32_t expected = (uint32_t)audioSampleRate * 2;

  Serial.printf("[MIC] cb=%u rate=%uB/s (expect %u when call active) sent=%uB/%uf drop=%uB buf=%u\n",
                (unsigned)audioCallbackCount, (unsigned)rate, (unsigned)expected,
                (unsigned)audioSentBytes, (unsigned)audioSentFrames,
                (unsigned)audioDroppedBytes, (unsigned)ringAvailable());

  Serial.printf("[MIC-DIAG] maxCbGap=%ums gaps>40ms=%u maxLoop=%ums\n",
                (unsigned)maxCbGapMs, (unsigned)bigGapCount, (unsigned)maxLoopMs);
  maxCbGapMs = 0;
  maxLoopMs  = 0;

  Serial.printf("[TTS] rx=%uB played=%uB drop=%uB underruns=%u buf=%u\n",
                (unsigned)txBytesReceived, (unsigned)txBytesSent,
                (unsigned)txBytesDropped, (unsigned)txUnderruns,
                (unsigned)txRingAvailable());

  // ===== AI ACTIVITY STATS (NEW) =====
  logAIStat();

  if (audioConnected && audioCallbackCount == 0)
  {
    Serial.println("WARN: SCO connected but no data callback -> check sdkconfig CONFIG_BT_HFP_AUDIO_DATA_PATH_HCI=y");
  }

  if (txBytesReceived > 0 && txBytesSent == 0)
  {
    Serial.println("WARN: TTS audio aaya par phone ko SCO pe nahi gaya -> hfpOutgoingCallback check karo");
  }
}

// ============================================================
// SETUP
// ============================================================
void setup()
{
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("########################################");
  Serial.println("#      SPARK VOICE DEVICE  v5          #");
  Serial.println("#      WIFI + WS + HFP + AUDIO STREAM  #");
  Serial.println("#      🤖 AI ACTIVITY LOGS ENABLED     #");
  Serial.println("########################################");
  Serial.printf("RESET REASON: %d  (1=power-on 3=sw 4=panic 5-7=wdt 15=brownout)\n",
                (int)esp_reset_reason());

  allocRings();
  generateDeviceId();

  connectWiFi();

  if (WiFi.status() == WL_CONNECTED)
  {
    connectBackend();

    Serial.println("Waiting for backend to connect BEFORE Bluetooth...");

    unsigned long t = millis();

    while (!backendConnected && millis() - t < BACKEND_BOOT_WAIT_MS)
    {
      webSocket.loop();
      delay(10);
    }

    if (backendConnected)
      Serial.println("Backend connected before Bluetooth start");
    else
      Serial.println("Backend not connected yet, continuing anyway...");
  }
  else
  {
    Serial.println("Backend waiting for WiFi...");
  }

  setupBluetooth();

  applyWifiPowerSave();
  Serial.printf("RADIO TUNING: WiFi PS=%s | COEX_PREFER_BT=%d\n",
                WIFI_PS_MODE_USED == WIFI_PS_NONE ? "NONE" : "MIN_MODEM",
                COEX_PREFER_BT);

#if HAVE_COEX && COEX_PREFER_BT
  esp_coex_preference_set(ESP_COEX_PREFER_BT);
  Serial.println("COEX: prefer BT");
#endif

  Serial.println();
  Serial.println("════════════════════════════════════════════");
  Serial.println("  ✅ SYSTEM STARTED - AI ACTIVITY LOGS LIVE");
  Serial.println("════════════════════════════════════════════");
  Serial.println();
}

// ============================================================
// LOOP
// ============================================================
void loop()
{
  unsigned long loopStart = millis();

  if (backendInitialized)
  {
    webSocket.loop();
  }

  handleWiFi();

  if (WiFi.status() == WL_CONNECTED)
  {
    connectBackend();
  }

  connectHFP();
  handleAutoAnswer();
  connectSCO();

  handlePendingEvents();
  handleAudioStreaming();

  printSystemStatus();

  delay(0);

  unsigned long lt = millis() - loopStart;
  if (lt > maxLoopMs) maxLoopMs = lt;

  delay(1);
}








--------------------------------------------


"""
Hardware Voice WebSocket Router - v4 (DEBUG + CONVERSATION LOGS).

Changes vs v3:
  1. logging.basicConfig(INFO) -> Sarvam / STT logger.info lines ab terminal me dikhengi.
  2. Terminal par clean conversation print:  👤 USER: ...  /  🤖 AI: ...
  3. extract_text(): LLM chunk content str ya list dono handle.
  4. Fallback: agar stream se text nahi mila to graph state se final AI reply utha ke bolta hai.
  5. Har turn ke liye alag thread_id (checkpoint corrupt / duplicate history problem khatam).
  6. Bahut chhote transcripts (<3 chars) ignore (noise "hmm" se barge-in nahi hoga).
  7. TTS_LEAD_SEC 0.18 -> 0.30.
  8. DEBUG_EVENTS=1 env se graph events print kar sakte ho.
"""

import os
import re
import sys
import json
import time
import wave
import logging
import asyncio
from array import array

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.ai.context.session_context_resolver import SessionContextResolver
from app.ai.prompts.prompt_builder import RuntimePromptBuilder
from app.ai.graph.graph import SparkAgentGraph
from app.modules.conversations.conversation_repository import ConversationRepository
from app.modules.organizations.organization_repository import OrganizationRepository
from app.database.mongodb import mongodb
from app.voice.telephony.sarvam_stt import SpeechTranscriber, synthesize_tts_pcm

# Logger ko INFO pe laao, warna [SARVAM TTS] / [SPEECH RECOGNITION] lines dikhti hi nahi
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Hardware Voice WebSocket"])

AUDIO_LOG_EVERY = int(os.getenv("AUDIO_LOG_EVERY", "0"))
SAVE_AUDIO_WAV = os.getenv("SAVE_AUDIO_WAV", "0") == "1"
SEND_STREAM_CHUNKS = os.getenv("SEND_STREAM_CHUNKS", "0") == "1"
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "16"))
DEBUG_EVENTS = os.getenv("DEBUG_EVENTS", "0") == "1"
MIN_TRANSCRIPT_CHARS = int(os.getenv("MIN_TRANSCRIPT_CHARS", "3"))

# ============================================================
# TTS PLAYBACK CONFIG
# ============================================================
TTS_SEND_CHUNK = 480
TTS_LEAD_SEC = 0.30
DEFAULT_VOICE_ID = "shubh"

_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")
MIN_SENT_CHARS = 14


def pop_sentences(buf: str):
    parts = _SENT_SPLIT.split(buf)
    if len(parts) <= 1:
        return [], buf
    return parts[:-1], parts[-1]


def trim_history(msgs: list, max_n: int) -> list:
    if len(msgs) <= max_n + 1:
        return msgs
    tail = list(msgs[-max_n:])
    while tail and isinstance(tail[0], AIMessage):
        tail.pop(0)
    return [msgs[0]] + tail


def normalize_phone(value):
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())[-10:]
    return digits if len(digits) == 10 else None


def extract_text(content) -> str:
    """LangChain chunk content str ho ya list[{'type':'text','text':...}], dono se text nikalo."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict) and p.get("type") == "text":
                out.append(p.get("text", ""))
        return "".join(out)
    return ""


def print_user(number: str, text: str):
    print(f"\n👤 USER ({number}): {text}", flush=True)


def print_ai(name: str, text: str):
    print(f"🤖 AI   ({name}): {text}\n", flush=True)


# =====================================================================
# AUDIO MONITOR
# =====================================================================
class AudioMonitor:
    SILENCE_RMS = 100

    def __init__(self, device_id: str, sample_rate: int = 8000):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.codec = "unknown"
        self.chunks = 0
        self.total_bytes = 0
        self.silent_chunks = 0
        self.started_at = time.time()
        self.win_start = time.time()
        self.win_bytes = 0
        self.wav = None
        if SAVE_AUDIO_WAV:
            self._open_wav()

    def _open_wav(self):
        self._close_wav()
        path = f"/tmp/{self.device_id}_{int(time.time())}.wav"
        self.wav = wave.open(path, "wb")
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(self.sample_rate)
        print(f"💾 [AUDIO SAVE] Recording to {path} @ {self.sample_rate} Hz", flush=True)

    def _close_wav(self):
        if self.wav:
            try:
                self.wav.close()
            except Exception:
                pass
            self.wav = None

    def set_format(self, sample_rate: int, codec: str):
        self.sample_rate = sample_rate
        self.codec = codec
        print(f"🎼 [AUDIO FORMAT] Device={self.device_id} | codec={codec} | sample_rate={sample_rate} Hz", flush=True)
        if SAVE_AUDIO_WAV:
            self._open_wav()

    def feed(self, data: bytes):
        self.chunks += 1
        n = len(data)
        self.total_bytes += n
        self.win_bytes += n

        usable = n - (n % 2)
        samples = array("h")
        samples.frombytes(data[:usable])
        if sys.byteorder == "big":
            samples.byteswap()

        count = len(samples)
        if count:
            peak = max(abs(s) for s in samples)
            rms = int((sum(s * s for s in samples) / count) ** 0.5)
        else:
            peak = rms = 0

        is_silent = rms < self.SILENCE_RMS
        if is_silent:
            self.silent_chunks += 1

        if self.wav:
            self.wav.writeframes(data[:usable])

        if AUDIO_LOG_EVERY > 0 and self.chunks == 1:
            print(f"🔬 [AUDIO FIRST CHUNK] {n} bytes | hex[0:32]={data[:32].hex(' ')}", flush=True)

        if AUDIO_LOG_EVERY > 0 and self.chunks % AUDIO_LOG_EVERY == 0:
            bar = "█" * min(30, rms // 200)
            icon = "🔇" if is_silent else "🔊"
            print(
                f"🎙️ #{self.chunks:<5} {n:>4} B | {count:>4} samples | rms={rms:>5} | peak={peak:>5} {icon} {bar}",
                flush=True,
            )

        now = time.time()
        if AUDIO_LOG_EVERY > 0 and now - self.win_start >= 1.0:
            elapsed = now - self.win_start
            bps = self.win_bytes / elapsed
            expected = self.sample_rate * 2
            print(
                f"📊 [AUDIO 1s SUMMARY] {bps:,.0f} B/s (expected ~{expected:,} B/s) | "
                f"total={self.total_bytes:,} B | chunks={self.chunks} | silent={self.silent_chunks}",
                flush=True,
            )
            self.win_start = now
            self.win_bytes = 0

    def close(self):
        dur = time.time() - self.started_at
        print(
            f"🏁 [AUDIO SESSION END] Device={self.device_id} | chunks={self.chunks} | "
            f"bytes={self.total_bytes:,} | silent_chunks={self.silent_chunks} | duration={dur:.1f}s",
            flush=True,
        )
        self._close_wav()


async def resolve_org_name(ctx) -> str:
    if not ctx:
        return "Our Business"
    name = getattr(ctx, "org_name", None) or getattr(ctx, "organization_name", None)
    if name and str(name).strip():
        return str(name).strip()

    if getattr(ctx, "org_id", None):
        org_doc = await mongodb.database["organizations"].find_one({"_id": ctx.org_id})
        if not org_doc:
            try:
                from bson import ObjectId
                org_doc = await mongodb.database["organizations"].find_one({"_id": ObjectId(ctx.org_id)})
            except Exception:
                pass
        if org_doc and org_doc.get("name"):
            return org_doc["name"].strip()
    return "Our Business"


# ============================================================
# PACED PCM SENDER
# ============================================================
class PacedPCMSender:
    def __init__(self, websocket: WebSocket, device_id: str):
        self.ws = websocket
        self.device_id = device_id
        self.t0 = None
        self.sent = 0
        self.rate = 0

    def reset(self):
        self.t0 = None
        self.sent = 0

    async def send(self, pcm: bytes, rate: int, text: str = "") -> bool:
        pcm = pcm[: len(pcm) - (len(pcm) % 2)]
        if not pcm:
            return False

        bps = rate * 2
        now = time.monotonic()
        if self.t0 is None or self.rate != rate or (self.t0 + self.sent / bps) < now:
            self.t0 = now
            self.sent = 0
            self.rate = rate

        print(f"🔊 [TTS OUTGOING] Device={self.device_id} | {len(pcm)} B @ {rate} Hz | text='{text[:60]}'", flush=True)

        try:
            await self.ws.send_text(json.dumps({"event": "ai_audio_start", "sample_rate": rate}))

            for i in range(0, len(pcm), TTS_SEND_CHUNK):
                chunk = pcm[i:i + TTS_SEND_CHUNK]
                await self.ws.send_bytes(chunk)
                self.sent += len(chunk)

                ahead = (self.t0 + self.sent / bps) - time.monotonic()
                if ahead > TTS_LEAD_SEC:
                    await asyncio.sleep(ahead - TTS_LEAD_SEC)

            await self.ws.send_text(json.dumps({"event": "ai_audio_end"}))
            return True

        except asyncio.CancelledError:
            raise
        except (WebSocketDisconnect, RuntimeError) as disc_err:
            logger.warning(f"⚠️ [TTS SEND] Device disconnected mid-playback: device={self.device_id}: {disc_err}")
            print(f"⚠️ [TTS SEND] Device disconnected mid-playback for device={self.device_id}", flush=True)
            return False
        except Exception as e:
            logger.error(f"❌ [TTS SEND ERROR] device={self.device_id}: {e}", exc_info=True)
            return False


@router.websocket("/ws/voice/{device_id}")
async def hardware_voice_websocket(websocket: WebSocket, device_id: str):
    """Direct WebSocket connection for physical hardware devices."""
    await websocket.accept()
    print("\n==================================================", flush=True)
    print(f"🔌 [WEBSOCKET CONNECTED] Device ID: {device_id}", flush=True)
    print("==================================================\n", flush=True)
    logger.info(f"🔌 Hardware WebSocket connected | device_id={device_id}")

    ctx = None
    session_id = None
    graph = None
    system_prompt = ""
    messages = []
    conversation_repo = ConversationRepository()

    audio_monitor = AudioMonitor(device_id)
    stt_transcriber = SpeechTranscriber(device_id)
    pacer = PacedPCMSender(websocket, device_id)

    device_sample_rate = 8000
    sco_ready = False
    pending_greeting_text = None
    pending_greeting_speaker = DEFAULT_VOICE_ID

    customer_number = "unknown"
    owner_number = "unknown"
    ai_display_name = "AI"
    turn_no = 0

    turn_lock = asyncio.Lock()

    bg_tasks: set = set()
    current_turn_task: asyncio.Task | None = None

    def run_in_background(coro):
        task = asyncio.create_task(coro)
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
        return task

    # ---------------- TTS pipeline ----------------
    tts_generation = 0
    tts_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    pcm_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    tts_tasks: list = []

    async def synth_worker():
        while True:
            text, speaker, rate, generation = await tts_queue.get()
            try:
                if generation != tts_generation:
                    continue

                t0 = time.monotonic()
                pcm = await synthesize_tts_pcm(text, sample_rate=rate, speaker=speaker)

                if generation != tts_generation:
                    print(f"🗑️ [TTS STALE] Dropping synthesized audio | gen={generation} current={tts_generation}", flush=True)
                    continue

                if pcm:
                    print(f"⏱️ [TTS SYNTH] {(time.monotonic() - t0) * 1000:.0f} ms | gen={generation} | '{text[:40]}'", flush=True)
                    await pcm_queue.put((pcm, rate, text, generation))
                else:
                    print(f"⚠️ [TTS] Empty/failed audio for device={device_id} | speaker={speaker} | '{text[:40]}'", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as tts_err:
                logger.error(f"TTS synth worker error: {tts_err}", exc_info=True)
            finally:
                try:
                    tts_queue.task_done()
                except Exception:
                    pass

    async def play_worker():
        while True:
            pcm, rate, text, generation = await pcm_queue.get()
            try:
                if generation != tts_generation:
                    continue
                await pacer.send(pcm, rate, text)
            except asyncio.CancelledError:
                raise
            except Exception as play_err:
                logger.error(f"TTS play worker error: {play_err}", exc_info=True)
            finally:
                try:
                    pcm_queue.task_done()
                except Exception:
                    pass

    def start_tts_workers():
        tts_tasks.append(asyncio.create_task(synth_worker()))
        tts_tasks.append(asyncio.create_task(play_worker()))

    async def stop_tts_workers():
        for t in tts_tasks:
            if not t.done():
                t.cancel()
        for t in tts_tasks:
            try:
                await asyncio.wait_for(t, timeout=1.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"tts worker cancel wait error: {e}")
        tts_tasks.clear()

    def _drain(q: asyncio.Queue):
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

    def clear_tts_queue():
        _drain(tts_queue)
        _drain(pcm_queue)

    async def cancel_tts_playback(reason: str = "new user speech"):
        nonlocal tts_generation
        tts_generation += 1
        generation = tts_generation

        print(f"🛑 [TTS CANCEL] device={device_id} gen={generation} reason={reason}", flush=True)

        try:
            await websocket.send_text(json.dumps({
                "event": "ai_audio_cancel",
                "generation": generation,
                "reason": reason,
            }))
        except Exception:
            pass

        await stop_tts_workers()
        clear_tts_queue()
        pacer.reset()
        start_tts_workers()

    async def restart_tts_workers():
        await cancel_tts_playback(reason="call reset")

    start_tts_workers()

    def speak(text: str, speaker: str):
        text = (text or "").strip()
        if not text:
            return
        try:
            tts_queue.put_nowait((text, speaker, device_sample_rate, tts_generation))
        except asyncio.QueueFull:
            print(f"⚠️ [TTS QUEUE FULL] Dropping text='{text[:50]}'", flush=True)

    async def cancel_active_turn():
        nonlocal current_turn_task
        task = current_turn_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            print("🛑 [TURN CANCEL] Cancelling previous LLM turn", flush=True)
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"Previous turn cancel error: {e}")
        current_turn_task = None

    async def submit_user_turn(user_query: str):
        nonlocal current_turn_task
        await cancel_active_turn()
        await cancel_tts_playback(reason="new user speech")
        current_turn_task = asyncio.create_task(run_agent_turn(user_query))

    def reset_call_state(keep_sco_state: bool = False):
        nonlocal sco_ready, pending_greeting_text, pending_greeting_speaker
        nonlocal device_sample_rate, ctx, graph, messages, session_id
        nonlocal customer_number, owner_number, ai_display_name, turn_no

        if not keep_sco_state:
            sco_ready = False
            device_sample_rate = 8000
            try:
                stt_transcriber.reset()
            except Exception:
                pass

        pending_greeting_text = None
        pending_greeting_speaker = DEFAULT_VOICE_ID
        ctx = None
        graph = None
        messages = []
        session_id = None
        customer_number = "unknown"
        owner_number = "unknown"
        ai_display_name = "AI"
        turn_no = 0

    # =================================================================
    # start_call
    # =================================================================
    async def start_call(payload: dict, send_greeting: bool = True) -> bool:
        nonlocal ctx, graph, messages, session_id, system_prompt
        nonlocal customer_number, owner_number, ai_display_name
        nonlocal pending_greeting_text, pending_greeting_speaker

        did_number = payload.get("did_number") or None
        caller_phone = payload.get("caller_phone") or None

        session_id = (
            f"SESSION_{device_id}_{caller_phone}"
            if caller_phone
            else f"SESSION_{device_id}"
        )

        print(f"📞 [CALL START] Device={device_id} | DID={did_number or 'from-device-lookup'} | Caller={caller_phone or 'unknown'} | Session={session_id}", flush=True)
        logger.info(f"📞 Call Start on Device {device_id} | DID={did_number} | Caller={caller_phone}")

        resolver = SessionContextResolver()
        try:
            ctx = await resolver.resolve(
                did_number=did_number,
                caller_phone=caller_phone,
                device_id=device_id,
            )
        except RuntimeError as resolve_err:
            logger.error(f"❌ [CONTEXT ERROR] {resolve_err}")
            print(f"❌ [CONTEXT ERROR] {resolve_err}", flush=True)
            print(
                f"   ➡️  Fix: POST /api/v1/organization/link-device/<org_id>  body: {{\"device_id\": \"{device_id}\"}}",
                flush=True,
            )
            ctx = None
            try:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "code": "device_not_linked",
                    "message": (
                        f"Device '{device_id}' is not linked to any organization. "
                        f"Use POST /api/v1/organization/link-device/<org_id> to link it."
                    ),
                }))
            except Exception:
                pass
            return False

        org_name = await resolve_org_name(ctx)

        ai_emp = getattr(ctx, "ai_employee", {}) or {}
        plat_cfg = getattr(ctx, "platform_config", {}) or {}
        biz_type = getattr(ctx, "business_type", "general")
        ai_display_name = ai_emp.get("name") or "AI"

        print(f"🏢 [CONTEXT RESOLVED] Org='{org_name}' | AI Employee='{ai_emp.get('name')}' | BizType='{biz_type}' | voice_id='{ai_emp.get('voice_id')}'", flush=True)

        _ctx_phone = getattr(ctx, "did_number", None)
        if not _ctx_phone and getattr(ctx, "org_id", None):
            try:
                from bson import ObjectId as _ObjId
                _org_doc = await mongodb.database["organizations"].find_one(
                    {"_id": _ObjId(ctx.org_id)},
                    {"phone": 1, "did_number": 1}
                )
                _ctx_phone = (_org_doc or {}).get("phone") or (_org_doc or {}).get("did_number")
            except Exception:
                pass
        org_number_display = _ctx_phone or "not configured"

        customer_number = normalize_phone(caller_phone) or "unknown"
        owner_number = normalize_phone(org_number_display) or org_number_display

        print("\n" + "=" * 60, flush=True)
        print("📋 [CALL SESSION METADATA]", flush=True)
        print(f"   🏢 org_name:     {org_name}", flush=True)
        print(f"   📞 org_number:   {org_number_display}", flush=True)
        print(f"   📱 device_id:    {device_id}", flush=True)
        print(f"   👤 user_number:  {caller_phone or 'unknown'}", flush=True)
        print("=" * 60 + "\n", flush=True)

        system_prompt = RuntimePromptBuilder.build(
            ai_employee=ai_emp,
            organization_name=org_name,
            platform_config=plat_cfg,
        )

        agent = SparkAgentGraph(business_type=biz_type)
        graph = agent.build()

        existing_conv = await conversation_repo.get_by_session_id(session_id)
        messages = [SystemMessage(content=system_prompt)]

        if existing_conv and existing_conv.get("messages"):
            for m in existing_conv["messages"][-MAX_HISTORY_MESSAGES:]:
                if m.get("role") == "user":
                    messages.append(HumanMessage(content=m.get("content", "")))
                elif m.get("role") == "assistant":
                    messages.append(AIMessage(content=m.get("content", "")))
            while len(messages) > 1 and isinstance(messages[1], AIMessage):
                messages.pop(1)

        voice_id = ai_emp.get("voice_id", DEFAULT_VOICE_ID)
        greeting_text = f"Namaste! Main {ai_emp.get('name', 'Assistant')} bol raha hu {org_name} se. Bataiye kaise help karu?"

        out_msg = {
            "event": "call_ready",
            "session_id": session_id,
            "greeting": greeting_text,
            "ai_name": ai_emp.get("name"),
            "voice_id": voice_id,
        }
        print(f"📤 [WEBSOCKET OUTGOING] Sending call_ready to Device={device_id}: {out_msg}", flush=True)
        try:
            await websocket.send_text(json.dumps(out_msg))
        except Exception:
            pass

        if send_greeting:
            print_ai(ai_display_name, greeting_text)
            if sco_ready:
                print("📤 [GREETING] SCO already ready, turant bhej rahe hain", flush=True)
                speak(greeting_text, voice_id)
            else:
                pending_greeting_text = greeting_text
                pending_greeting_speaker = voice_id
                print("⏳ [GREETING QUEUED] SCO abhi ready nahi hai, audio_format ka wait kar rahe hain", flush=True)

        return True

    # =================================================================
    # run_agent_turn
    # =================================================================
    async def run_agent_turn(user_query: str):
        nonlocal messages, turn_no

        async with turn_lock:
            if not user_query or not graph or not ctx:
                return

            messages.append(HumanMessage(content=user_query))
            messages = trim_history(messages, MAX_HISTORY_MESSAGES)

            # Har turn ka alag thread_id: cancelled turn ka adhura checkpoint next turn ko kharab nahi karega
            turn_no += 1
            thread_id = f"{session_id}_t{turn_no}"

            ai_reply_content = ""
            sentence_buf = ""
            pending = ""
            spoken_any = False
            turn_t0 = time.monotonic()

            ai_emp = getattr(ctx, "ai_employee", {}) or {}
            voice_id = ai_emp.get("voice_id", DEFAULT_VOICE_ID)

            try:
                async for event in graph.astream_events(
                    {
                        "messages": messages,
                        "owner_id": getattr(ctx, "owner_id", None),
                        "org_id": getattr(ctx, "org_id", None),
                        "business_type": getattr(ctx, "business_type", "general"),
                        "business_type_id": getattr(ctx, "business_type_id", None),
                        "ai_employee_id": getattr(ctx, "ai_employee_id", None),
                        "ai_employee": ai_emp,
                        "platform_config": getattr(ctx, "platform_config", {}),
                    },
                    config={"configurable": {"thread_id": thread_id}},
                    version="v2",
                ):
                    if DEBUG_EVENTS:
                        print("EVT:", event.get("event"), event.get("name"), flush=True)

                    if event.get("event") != "on_chat_model_stream":
                        continue

                    chunk = event.get("data", {}).get("chunk")
                    content = extract_text(getattr(chunk, "content", ""))
                    if not content:
                        continue

                    ai_reply_content += content
                    sentence_buf += content

                    if SEND_STREAM_CHUNKS:
                        try:
                            await websocket.send_text(json.dumps({
                                "event": "ai_stream_chunk",
                                "chunk": content,
                            }))
                        except Exception:
                            pass

                    if sco_ready:
                        sentences, sentence_buf = pop_sentences(sentence_buf)
                        for s in sentences:
                            pending = f"{pending} {s}".strip()
                            if len(pending) >= MIN_SENT_CHARS:
                                if not spoken_any:
                                    print(f"⏱️ [LATENCY] first sentence ready in {(time.monotonic() - turn_t0) * 1000:.0f} ms after transcript", flush=True)
                                    spoken_any = True
                                speak(pending, voice_id)
                                pending = ""

            except asyncio.CancelledError:
                if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == user_query:
                    messages.pop()
                print(f"🛑 [LLM TURN CANCELLED] '{user_query[:60]}'", flush=True)
                raise
            except Exception as llm_err:
                logger.error(f"❌ [LLM ERROR] session={session_id}: {llm_err}", exc_info=True)
                print(f"❌ [LLM ERROR] {llm_err}", flush=True)
                return

            # ---------- FALLBACK: stream se kuch nahi aaya to graph state se final reply lo ----------
            if not ai_reply_content:
                print("⚠️ [LLM EMPTY] stream se text nahi mila -> graph state se try kar rahe hain", flush=True)
                try:
                    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
                    msgs_state = (snap.values or {}).get("messages", []) if snap else []
                    for m in reversed(msgs_state):
                        if isinstance(m, AIMessage):
                            txt = extract_text(m.content).strip()
                            if txt:
                                ai_reply_content = txt
                                # poora reply ek saath bolo (streaming nahi hui thi)
                                sentence_buf = ""
                                pending = ""
                                if sco_ready:
                                    for s in [x for x in _SENT_SPLIT.split(txt) if x.strip()]:
                                        speak(s, voice_id)
                                else:
                                    print("⚠️ [TTS SKIPPED] SCO ready nahi hai", flush=True)
                            break
                except Exception as e:
                    logger.error(f"❌ [FALLBACK ERROR] {e}", exc_info=True)

                if not ai_reply_content:
                    print("❌ [LLM EMPTY] graph ne koi reply nahi diya (logs upar dekho)", flush=True)
                    return
            else:
                tail = f"{pending} {sentence_buf}".strip()
                if tail:
                    if sco_ready:
                        speak(tail, voice_id)
                    else:
                        print("⚠️ [TTS SKIPPED] SCO abhi ready nahi hai, reply audio nahi bhej rahe", flush=True)

            # ---------- CONVERSATION PRINT ----------
            print_ai(ai_display_name, ai_reply_content)

            messages.append(AIMessage(content=ai_reply_content))

            async def _save():
                try:
                    await conversation_repo.save_message(
                        session_id=session_id,
                        owner_id=getattr(ctx, "owner_id", None),
                        org_id=getattr(ctx, "org_id", None),
                        employee_id=getattr(ctx, "ai_employee_id", None),
                        user_message=user_query,
                        assistant_reply=ai_reply_content,
                        cart=[],
                        customer_id=getattr(ctx, "customer_id", None),
                    )
                except Exception as save_err:
                    logger.error(f"Failed to save conversation to DB: {save_err}")

            run_in_background(_save())

            try:
                await websocket.send_text(json.dumps({
                    "event": "ai_response_complete",
                    "full_text": ai_reply_content,
                    "voice_id": voice_id,
                }))
            except Exception:
                pass

    # =================================================================
    # Live STT callback
    # =================================================================
    async def handle_live_transcription(transcribed_text: str):
        transcribed_text = (transcribed_text or "").strip()
        if not transcribed_text:
            return

        if len(transcribed_text) < MIN_TRANSCRIPT_CHARS:
            print(f"🔇 [STT IGNORED] bahut chhota transcript: '{transcribed_text}'", flush=True)
            return

        # ---------- CONVERSATION PRINT ----------
        print_user(customer_number, transcribed_text)
        logger.info(f"🗣️ Speech Transcribed | Device={device_id} | Text='{transcribed_text}'")

        if not (graph and ctx):
            print("⚠️ [NO CTX] Transcript aaya par call context nahi hai -- auto start_call try kar rahe hain", flush=True)
            ok = await start_call({}, send_greeting=False)
            if not ok:
                return

        try:
            await submit_user_turn(transcribed_text)
        except asyncio.CancelledError:
            raise
        except Exception as turn_err:
            logger.error(f"❌ [TURN ERROR] {turn_err}", exc_info=True)

    # =================================================================
    # MAIN LOOP
    # =================================================================
    try:
        while True:
            raw_msg = await websocket.receive()

            if raw_msg.get("type") == "websocket.disconnect":
                print("\n==================================================", flush=True)
                print(f"🔴 [WEBSOCKET DISCONNECTED] Device ID: {device_id}", flush=True)
                print("==================================================\n", flush=True)
                logger.info(f"🔌 Hardware WebSocket Disconnected: {device_id}")
                break

            # ---------------- JSON control / events ----------------
            if raw_msg.get("text") is not None:
                raw_text = raw_msg["text"]
                print(f"\n📥 [WEBSOCKET INCOMING TEXT] Device={device_id} | Raw Payload: {raw_text}", flush=True)

                try:
                    payload = json.loads(raw_text)
                except Exception as parse_err:
                    print(f"⚠️ [WEBSOCKET ERROR] JSON parse error: {parse_err} | Text: {raw_text}", flush=True)
                    logger.error(f"Failed to parse WebSocket JSON payload: {parse_err}")
                    continue

                event_type = payload.get("event")
                print(f"🔍 [PARSED EVENT] Event: '{event_type}'", flush=True)

                try:
                    # ---------------- device_ready ----------------
                    if event_type == "device_ready":
                        print(f"🟢 [DEVICE READY ACK] Device={device_id} is connected & ready", flush=True)
                        logger.info(f"🟢 Device Ready | device_id={device_id}")

                        _org_repo = OrganizationRepository()
                        _org_for_device = await _org_repo.get_by_device_id(device_id)

                        if _org_for_device:
                            print(f"✅ [DEVICE REGISTERED] Device={device_id} -> Org='{_org_for_device.get('name', 'unknown')}'", flush=True)
                        else:
                            from datetime import datetime, timezone as _tz
                            _devices_col = mongodb.database["spark_devices"]
                            _existing = await _devices_col.find_one({"device_id": device_id})
                            if not _existing:
                                await _devices_col.insert_one({
                                    "device_id": device_id,
                                    "status": "unregistered",
                                    "org_id": None,
                                    "first_seen": datetime.now(_tz.utc),
                                    "last_seen": datetime.now(_tz.utc),
                                })
                                print(f"📝 [DEVICE AUTO-SAVED] Device={device_id} saved to 'spark_devices' (unregistered)", flush=True)
                                logger.warning(f"New unregistered device saved: {device_id} — assign org via dashboard")
                            else:
                                await _devices_col.update_one(
                                    {"device_id": device_id},
                                    {"$set": {"last_seen": datetime.now(_tz.utc)}}
                                )
                                print(f"⚠️ [DEVICE UNREGISTERED] Device={device_id} known but not assigned to any org!", flush=True)

                        out_msg = {
                            "event": "server_ready",
                            "status": "connected",
                            "device_id": device_id,
                            "registered": _org_for_device is not None,
                        }
                        print(f"📤 [WEBSOCKET OUTGOING] Sending server_ready to Device={device_id}: {out_msg}", flush=True)
                        await websocket.send_text(json.dumps(out_msg))

                    # ---------------- audio_format ----------------
                    elif event_type == "audio_format":
                        s_rate = int(payload.get("sample_rate", 8000))
                        codec_name = str(payload.get("codec", "unknown"))
                        audio_monitor.set_format(sample_rate=s_rate, codec=codec_name)
                        stt_transcriber.set_sample_rate(s_rate)
                        device_sample_rate = s_rate

                        sco_ready = True
                        print(f"✅ [SCO READY] Device={device_id} | codec={codec_name} | rate={s_rate} | audio channel open", flush=True)

                        if pending_greeting_text:
                            queued_text = pending_greeting_text
                            queued_speaker = pending_greeting_speaker
                            pending_greeting_text = None
                            print(f"📤 [QUEUED GREETING] Ab SCO ready hai, greeting bhej rahe hain: '{queued_text[:50]}'", flush=True)
                            speak(queued_text, queued_speaker)

                    # ---------------- ESP32 status events ----------------
                    elif event_type in ["phone_bluetooth_connected", "call_incoming", "call_answered", "call_audio_started", "call_audio_stopped"]:
                        print(f"ℹ️ [ESP32 STATUS EVENT] Type={event_type} | Device={device_id}", flush=True)

                    # ---------------- call_started ----------------
                    elif event_type == "call_started":
                        reset_call_state(keep_sco_state=True)
                        await start_call(payload)

                    # ---------------- user_text ----------------
                    elif event_type == "user_text":
                        user_query = payload.get("text", "").strip()
                        if not user_query or not graph or not ctx:
                            print(f"⚠️ [USER TEXT SKIPPED] Query='{user_query}' | Graph Ready={graph is not None} | Ctx Ready={ctx is not None}", flush=True)
                            continue

                        print_user(customer_number, user_query)
                        await submit_user_turn(user_query)

                    # ---------------- call_ended ----------------
                    elif event_type == "call_ended":
                        print(f"🔴 [CALL ENDED EVENT] Device={device_id}", flush=True)
                        logger.info(f"🔴 Call Ended by Hardware | device_id={device_id}")

                        await cancel_active_turn()
                        await restart_tts_workers()
                        try:
                            audio_monitor.close()
                        except Exception:
                            pass
                        audio_monitor = AudioMonitor(device_id)
                        stt_transcriber.reset()
                        reset_call_state(keep_sco_state=False)

                    else:
                        print(f"❓ [UNHANDLED HARDWARE EVENT] Type='{event_type}' | Device={device_id}", flush=True)
                        logger.warning(f"Unhandled hardware event: {event_type} | device_id={device_id}")

                except asyncio.CancelledError:
                    raise
                except Exception as event_err:
                    logger.error(f"❌ Error processing event '{event_type}': {event_err}", exc_info=True)
                    print(f"❌ [EVENT ERROR] {event_type}: {event_err}", flush=True)

            # ---------------- Binary audio (customer voice) ----------------
            elif raw_msg.get("bytes") is not None:
                audio_bytes = raw_msg["bytes"]

                try:
                    audio_monitor.feed(audio_bytes)
                except Exception as audio_err:
                    print(f"⚠️ [AUDIO MONITOR ERROR] {audio_err}", flush=True)

                try:
                    stt_transcriber.feed(audio_bytes, handle_live_transcription)
                except Exception as stt_err:
                    print(f"⚠️ [STT TRANSCRIBER ERROR] {stt_err}", flush=True)

    except (WebSocketDisconnect, RuntimeError) as disc_err:
        print("\n==================================================", flush=True)
        print(f"🔴 [WEBSOCKET DISCONNECTED] Device ID: {device_id} | reason={disc_err}", flush=True)
        print("==================================================\n", flush=True)
        logger.info(f"🔌 Hardware WebSocket Disconnected: {device_id}")
    except asyncio.CancelledError:
        logger.info(f"🔌 WebSocket handler cancelled: {device_id}")
    except Exception as exc:
        logger.error(f"❌ Error in Hardware Voice Socket: {exc}", exc_info=True)
    finally:
        try:
            await cancel_active_turn()
        except Exception:
            pass

        try:
            await stop_tts_workers()
        except Exception:
            pass

        try:
            await stt_transcriber.close()
        except Exception:
            pass

        try:
            audio_monitor.close()
        except Exception:
            pass

        try:
            await websocket.close()
        except Exception:
            pass




--------------------------------------

"""
Hardware Voice STT + TTS helper  (v2 - DEBUG PRINTS).

STT:  ESP32 PCM -> VAD segmenter -> Google Web Speech (SpeechRecognition) -> text
TTS:  text -> Sarvam Bulbul -> 16-bit mono PCM -> ESP32 HFP

Har STT stage terminal pe print hota hai:
  🎚️ [VAD]        mic level (har 3 sec)        -> mic audio aa raha hai ya nahi
  🎙️ [SPEECH]     speech start detect hui
  🧩 [UTTERANCE]  utterance pakdi gayi
  🗑️ [VAD DROP]   utterance bahut chhoti thi
  🔇 [STT GATE]   energy kam thi
  🎤 [STT]        Google ko bheja
  🎯 [STT RESULT] Google ne kya text diya

STT_DEBUG=0 se VAD level lines band kar sakte ho.
"""

import io
import os
import re
import sys
import time
import wave
import base64
import asyncio
import logging

from array import array
from collections import deque
from typing import Awaitable, Callable, Optional

import httpx
import speech_recognition as sr

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

STT_LANGUAGE = os.getenv("STT_LANGUAGE", "hi-IN")
STT_DEBUG = os.getenv("STT_DEBUG", "1") == "1"

# "hii" jaise chhote words ke liye thresholds thode kam rakhe hain
STT_SILENCE_MS = int(os.getenv("STT_SILENCE_MS", "600"))
STT_MIN_SPEECH_MS = int(os.getenv("STT_MIN_SPEECH_MS", "150"))
STT_MIN_ENERGY = int(os.getenv("STT_MIN_ENERGY", "100"))
STT_VAD_RMS = int(os.getenv("STT_VAD_RMS", "200"))

STT_NOISE_MULT = 2.5
STT_KEEP_RATIO = 0.70
STT_MAX_UTTER_MS = 25000
STT_PREROLL_MS = 250
STT_TIMEOUT = int(os.getenv("STT_TIMEOUT", "20"))
STT_PHRASE_TIME_LIMIT = int(os.getenv("STT_PHRASE_TIME_LIMIT", "20"))

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
TTS_MODEL = os.getenv("TTS_MODEL", "bulbul:v3")
TTS_SPEAKER = os.getenv("TTS_SPEAKER", "shubh")
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "hi-IN")
TTS_DEBUG_DUMP = os.getenv("TTS_DEBUG_DUMP", "0") == "1"
TTS_MAX_CHARS = 2500 if TTS_MODEL.startswith("bulbul:v3") else 1500


# ============================================================
# SHARED HTTP CLIENT
# ============================================================

_http: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=60),
        )
    return _http


async def close_http_client():
    global _http
    if _http is not None and not _http.is_closed:
        await _http.aclose()
    _http = None


# ============================================================
# PCM HELPERS
# ============================================================

def _to_samples(pcm: bytes) -> array:
    usable = len(pcm) - (len(pcm) % 2)
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _from_samples(samples: array) -> bytes:
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes()


def _rms(data: bytes) -> int:
    samples = _to_samples(data)
    if not samples:
        return 0
    total = sum(s * s for s in samples)
    return int((total / len(samples)) ** 0.5)


def _upsample_2x(pcm: bytes) -> bytes:
    """8kHz -> 16kHz (linear interpolation)."""
    src = _to_samples(pcm)
    out = array("h")
    n = len(src)
    for i in range(n):
        a = src[i]
        b = src[i + 1] if i + 1 < n else a
        out.append(a)
        out.append((a + b) // 2)
    return _from_samples(out)


def _downsample_2x(pcm: bytes) -> bytes:
    """16kHz -> 8kHz (pair averaging)."""
    usable = len(pcm) - (len(pcm) % 4)
    src = _to_samples(pcm[:usable])
    out = array("h")
    for i in range(0, len(src) - 1, 2):
        out.append((src[i] + src[i + 1]) // 2)
    return _from_samples(out)


def _mono_from_pcm16(pcm: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm
    samples = _to_samples(pcm)
    out = array("h")
    frame_count = len(samples) // channels
    for frame in range(frame_count):
        start = frame * channels
        total = 0
        for ch in range(channels):
            total += samples[start + ch]
        value = max(-32768, min(32767, int(total / channels)))
        out.append(value)
    return _from_samples(out)


def _linear_resample(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
    if source_rate <= 0 or target_rate <= 0:
        return pcm
    samples = _to_samples(pcm)
    if not samples:
        return b""
    if source_rate == target_rate:
        return pcm

    output_length = int(len(samples) * target_rate / source_rate)
    out = array("h")
    ratio = source_rate / target_rate

    for i in range(output_length):
        position = i * ratio
        left = int(position)
        fraction = position - left
        if left >= len(samples) - 1:
            value = samples[-1]
        else:
            a = samples[left]
            b = samples[left + 1]
            value = int(a + (b - a) * fraction)
        out.append(max(-32768, min(32767, value)))

    return _from_samples(out)


def _wav_to_pcm(wav_bytes: bytes, target_rate: int) -> bytes:
    """WAV -> mono 16-bit PCM at target_rate."""
    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            source_rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())

    logger.info(f"🔍 [TTS WAV] rate={source_rate} channels={channels} width={sample_width} bytes={len(raw)}")

    if sample_width == 2:
        pcm = raw
    elif sample_width == 1:
        out = array("h")
        for value in raw:
            out.append((value - 128) << 8)
        pcm = _from_samples(out)
    elif sample_width == 3:
        out = array("h")
        for i in range(0, len(raw) - 2, 3):
            value = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if value & 0x800000:
                value -= 1 << 24
            value >>= 8
            out.append(max(-32768, min(32767, value)))
        pcm = _from_samples(out)
    elif sample_width == 4:
        src = array("i")
        src.frombytes(raw)
        if sys.byteorder == "big":
            src.byteswap()
        out = array("h")
        for value in src:
            out.append(max(-32768, min(32767, value >> 16)))
        pcm = _from_samples(out)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if channels != 1:
        pcm = _mono_from_pcm16(pcm, channels)

    if source_rate != target_rate:
        if source_rate == 16000 and target_rate == 8000:
            pcm = _downsample_2x(pcm)
        elif source_rate == 8000 and target_rate == 16000:
            pcm = _upsample_2x(pcm)
        else:
            pcm = _linear_resample(pcm, source_rate, target_rate)

    return pcm[: len(pcm) - (len(pcm) % 2)]


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ============================================================
# ADAPTIVE VAD
# ============================================================

class UtteranceSegmenter:

    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        self.noise_floor = 150.0
        self.last_rms = 0
        self.last_threshold = 0.0
        self.reset()

    def reset(self):
        self.speaking = False
        self.buf = bytearray()
        self.preroll = deque()
        self.preroll_ms = 0.0
        self.speech_ms = 0.0
        self.silence_ms = 0.0
        self.total_ms = 0.0
        self.last_loud_len = 0

    def _threshold(self):
        return max(float(STT_VAD_RMS), self.noise_floor * STT_NOISE_MULT)

    def feed(self, chunk: bytes):
        if not chunk:
            return None

        duration_ms = len(chunk) / 2 / self.sample_rate * 1000
        rms = _rms(chunk)
        threshold = self._threshold()

        self.last_rms = rms
        self.last_threshold = threshold

        # ---------------- Waiting for speech ----------------
        if not self.speaking:
            if rms >= threshold:
                self.speaking = True
                self.buf = bytearray(b"".join(data for data, _ in self.preroll))
                self.buf += chunk
                self.last_loud_len = len(self.buf)
                self.speech_ms = duration_ms
                self.silence_ms = 0.0
                self.total_ms = self.preroll_ms + duration_ms
                self.preroll.clear()
                self.preroll_ms = 0.0
                print(f"🎙️ [SPEECH] start | rms={rms} thr={threshold:.0f}", flush=True)
            else:
                # background noise seekho
                self.noise_floor = min(400.0, 0.95 * self.noise_floor + 0.05 * rms)
                self.preroll.append((chunk, duration_ms))
                self.preroll_ms += duration_ms
                while self.preroll_ms > STT_PREROLL_MS and self.preroll:
                    _, old = self.preroll.popleft()
                    self.preroll_ms -= old
            return None

        # ---------------- Already speaking ----------------
        loud = rms >= threshold * STT_KEEP_RATIO
        self.buf += chunk
        self.total_ms += duration_ms

        if loud:
            self.silence_ms = 0.0
            self.speech_ms += duration_ms
            self.last_loud_len = len(self.buf)
        else:
            self.silence_ms += duration_ms

        # ---------------- End utterance ----------------
        if self.silence_ms >= STT_SILENCE_MS or self.total_ms >= STT_MAX_UTTER_MS:
            pcm = bytes(self.buf)
            speech_rms = _rms(pcm[: self.last_loud_len])
            speech_ms = self.speech_ms
            enough = speech_ms >= STT_MIN_SPEECH_MS
            self.reset()

            if enough:
                return (pcm, speech_rms)

            print(f"🗑️ [VAD DROP] utterance chhoti thi: speech={speech_ms:.0f}ms < {STT_MIN_SPEECH_MS}ms", flush=True)
            return None

        return None


# ============================================================
# SPEECH RECOGNITION STT
# ============================================================

_recognizer = sr.Recognizer()


def _speech_recognition_sync(wav_bytes: bytes) -> str:
    """Blocking Google call. asyncio.to_thread ke andar chalao."""
    try:
        with io.BytesIO(wav_bytes) as buffer:
            with sr.AudioFile(buffer) as source:
                audio = _recognizer.record(source)

        text = _recognizer.recognize_google(audio, language=STT_LANGUAGE)
        return (text or "").strip()

    except sr.UnknownValueError:
        print("🤷 [STT RESULT] Google ko speech samajh nahi aayi (UnknownValueError)", flush=True)
        return ""

    except sr.RequestError as e:
        print(f"❌ [STT RESULT] Google service error (internet/rate-limit?): {e}", flush=True)
        return ""

    except Exception as e:
        print(f"❌ [STT RESULT] Exception: {e}", flush=True)
        logger.error(f"STT exception: {e}", exc_info=True)
        return ""


async def transcribe_pcm(pcm: bytes, sample_rate: int, energy_rms: Optional[int] = None) -> str:
    if not pcm:
        return ""

    energy = energy_rms if energy_rms is not None else _rms(pcm)

    if energy < STT_MIN_ENERGY:
        print(f"🔇 [STT GATE] energy kam hai: rms={energy} < {STT_MIN_ENERGY}", flush=True)
        return ""

    clean_pcm = pcm
    if sample_rate == 8000:
        clean_pcm = await asyncio.to_thread(_upsample_2x, clean_pcm)
        recognition_rate = 16000
    else:
        recognition_rate = sample_rate

    wav_bytes = _pcm_to_wav(clean_pcm, recognition_rate)

    print(f"🎤 [STT] Google ko bhej rahe hain: {len(wav_bytes)} B @ {recognition_rate} Hz | rms={energy} | lang={STT_LANGUAGE}", flush=True)

    t0 = time.monotonic()
    text = await asyncio.to_thread(_speech_recognition_sync, wav_bytes)
    elapsed = (time.monotonic() - t0) * 1000

    if text:
        print(f"🎯 [STT RESULT] {elapsed:.0f} ms | '{text}'", flush=True)
    else:
        print(f"🎯 [STT RESULT] {elapsed:.0f} ms | EMPTY", flush=True)

    return text


# ============================================================
# SPEECH TRANSCRIBER
# ============================================================

class SpeechTranscriber:

    def __init__(self, device_id: str, sample_rate: int = 8000):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.segmenter = UtteranceSegmenter(sample_rate)
        self._queue = None
        self._worker = None
        self._on_text = None

        # debug: mic level har 3 sec
        self._dbg_t = time.monotonic()
        self._dbg_max_rms = 0
        self._dbg_bytes = 0

    def set_sample_rate(self, sample_rate: int):
        if sample_rate == self.sample_rate:
            self.segmenter.reset()
            return
        self.sample_rate = sample_rate
        self.segmenter = UtteranceSegmenter(sample_rate)

    def _drain_queue(self):
        if self._queue is None:
            return
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _ensure_worker(self, on_text):
        self._on_text = on_text
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=8)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._worker_loop())

    def _debug_level(self, nbytes: int):
        if not STT_DEBUG:
            return
        self._dbg_bytes += nbytes
        self._dbg_max_rms = max(self._dbg_max_rms, self.segmenter.last_rms)
        now = time.monotonic()
        if now - self._dbg_t >= 3.0:
            dt = now - self._dbg_t
            print(
                f"🎚️ [VAD] mic={self._dbg_bytes / dt:,.0f} B/s (expect {self.sample_rate * 2:,}) | "
                f"max_rms={self._dbg_max_rms} | thr={self.segmenter.last_threshold:.0f} | "
                f"noise={self.segmenter.noise_floor:.0f} | speaking={self.segmenter.speaking}",
                flush=True,
            )
            self._dbg_t = now
            self._dbg_max_rms = 0
            self._dbg_bytes = 0

    def feed(self, data: bytes, on_text: Callable[[str], Awaitable[None]]):
        result = self.segmenter.feed(data)
        self._debug_level(len(data))

        if not result:
            return

        pcm, energy = result
        self._ensure_worker(on_text)

        try:
            self._queue.put_nowait((pcm, energy, self.sample_rate))
        except asyncio.QueueFull:
            print("⚠️ [STT] Queue full; utterance dropped", flush=True)

    async def _worker_loop(self):
        while True:
            pcm, energy, rate = await self._queue.get()
            try:
                duration = len(pcm) / 2 / rate
                print(f"🧩 [UTTERANCE] {duration:.1f}s | rms={energy} | device={self.device_id}", flush=True)

                text = await transcribe_pcm(pcm, rate, energy)

                if text and self._on_text:
                    await self._on_text(text)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"❌ [STT WORKER] {e}", exc_info=True)
                print(f"❌ [STT WORKER] {e}", flush=True)
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def reset(self):
        self.segmenter.reset()
        self._drain_queue()

    async def close(self):
        self._drain_queue()
        if self._worker and not self._worker.done():
            self._worker.cancel()
            try:
                await asyncio.wait_for(self._worker, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        self._worker = None


# ============================================================
# TTS TEXT CLEANING
# ============================================================

_URL_RE = re.compile(r"https?://\S+")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+")
_MD_RE = re.compile(r"[*_`#>~|]+")
_WS_RE = re.compile(r"\s+")


def clean_for_tts(text: str) -> str:
    text = text or ""
    text = _URL_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _MD_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


# ============================================================
# SARVAM TTS
# ============================================================

async def synthesize_tts_pcm(text: str, sample_rate: int = 8000, speaker: str = None) -> bytes:
    """Text -> Sarvam Bulbul -> mono 16-bit PCM at sample_rate."""

    from app.core.config import settings

    text = clean_for_tts(text)
    if not text:
        return b""

    sarvam_key = os.getenv("SARVAM_API_KEY", "") or getattr(settings, "SARVAM_API_KEY", "")

    if not sarvam_key:
        print("❌ [TTS] SARVAM_API_KEY missing", flush=True)
        return b""

    safe_text = text[:TTS_MAX_CHARS]

    payload = {
        "text": safe_text,
        "target_language_code": TTS_LANGUAGE,
        "model": TTS_MODEL,
        "speaker": speaker or TTS_SPEAKER,
        "speech_sample_rate": sample_rate,
    }

    try:
        t0 = time.monotonic()

        response = await _client().post(
            SARVAM_TTS_URL,
            headers={
                "api-subscription-key": sarvam_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        elapsed = (time.monotonic() - t0) * 1000

        if response.status_code != 200:
            print(f"❌ [SARVAM TTS] HTTP {response.status_code} | speaker={payload['speaker']} model={TTS_MODEL} | {response.text[:300]}", flush=True)
            return b""

        data = response.json()
        audios = data.get("audios") or []

        if not audios:
            print("❌ [SARVAM TTS] Empty audios response", flush=True)
            return b""

        wav_bytes = base64.b64decode(audios[0])
        pcm = await asyncio.to_thread(_wav_to_pcm, wav_bytes, sample_rate)
        if not pcm:
            print("❌ [TTS] Normalized PCM empty", flush=True)
            return b""
        if TTS_DEBUG_DUMP:
            try:
                path = f"/tmp/tts_{int(time.time() * 1000)}.wav"
                with open(path, "wb") as f:
                    f.write(_pcm_to_wav(pcm, sample_rate))
                print(f"💾 [TTS DUMP] {path}", flush=True)
            except Exception as e:
                logger.warning(f"TTS dump failed: {e}")
        audio_seconds = len(pcm) / 2 / sample_rate
        print(
            f"🔊 [SARVAM TTS] {elapsed:.0f} ms | {audio_seconds:.2f}s | {len(pcm)} B | "
            f"{sample_rate} Hz | rms={_rms(pcm)} | '{safe_text[:60]}'",
            flush=True,
        )
        return pcm
    except Exception as e:
        print(f"❌ [SARVAM TTS EXCEPTION] {e}", flush=True)
        logger.error(f"Sarvam TTS exception: {e}", exc_info=True)
        return b""