#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <math.h>
#include "esp_wifi.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include "esp_heap_caps.h"


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



// Diagnostic counters
static uint32_t micBytes = 0;
static uint32_t micCallbacks = 0;
static uint32_t micLastReport = 0;
static uint32_t micMaxGapMs = 0;
static uint32_t micLastCallbackMs = 0;


// ---- Tuning switches -----------------------------------------------------
#define WIFI_PS_MODE_USED   WIFI_PS_NONE
#define COEX_PREFER_BT      0
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
volatile bool audioConnecting   = false;
volatile bool audioConnected    = false;
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

uint32_t audioSendFailures = 0;

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
#define TX_PREBUFFER_MS   200

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

volatile bool dbgTtsStarted  = false;
volatile bool dbgScoInferred = false;

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


void printMemoryStats() {
    Serial.printf(
        "[MEM] Free=%u | MinFree=%u | LargestBlock=%u\n",
        ESP.getFreeHeap(),
        ESP.getMinFreeHeap(),
        heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)
    );
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
    if (!txRing || !data || len == 0) return;

    len &= ~1u;  // Keep PCM samples aligned.
    if (len == 0) return;

    uint32_t written = 0;
    uint32_t waitStart = millis();

    while (written < len)
    {
        if (!callActive || !audioConnected)
        {
            txBytesDropped += (len - written);
            return;
        }

        portENTER_CRITICAL(&txRingMux);

        uint32_t used = txRingAvailableUnsafe();
        uint32_t freeBytes = txRingSize - 1 - used;
        uint32_t remaining = len - written;

        // Write only complete 16-bit PCM samples.
        uint32_t n = min(remaining, freeBytes) & ~1u;

        if (n > 0)
        {
            uint32_t first = min(n, txRingSize - txRingHead);

            memcpy(txRing + txRingHead, data + written, first);

            if (n > first)
            {
                memcpy(
                    txRing,
                    data + written + first,
                    n - first
                );
            }

            txRingHead = (txRingHead + n) % txRingSize;
            written += n;
        }

        portEXIT_CRITICAL(&txRingMux);

        if (written < len)
        {
            // Let the Bluetooth task consume queued audio.
            if (millis() - waitStart >= 1000)
            {
                txBytesDropped += (len - written);

                Serial.printf(
                    "[TX OVERFLOW] dropped=%lu remaining=%lu ring=%lu\n",
                    (unsigned long)(len - written),
                    (unsigned long)(len - written),
                    (unsigned long)txRingAvailable()
                );

                return;
            }

            delay(1);
        }
    }

    txBytesReceived += written;
    txLastRxMs = millis();
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


uint32_t ringPeek(uint8_t* out, uint32_t maxLen)
{
    if (!audioRing || out == nullptr || maxLen == 0) return 0;

    portENTER_CRITICAL(&audioRingMux);

    uint32_t available = ringAvailableUnsafe();
    uint32_t n = min(maxLen, available) & ~1u;

    if (n > 0) {
        uint32_t first = min(n, audioRingSize - ringTail);
        memcpy(out, audioRing + ringTail, first);

        if (n > first) {
            memcpy(out + first, audioRing, n - first);
        }
    }

    portEXIT_CRITICAL(&audioRingMux);
    return n;
}

void ringDiscard(uint32_t len)
{
    if (!audioRing || len == 0) return;

    len &= ~1u;

    portENTER_CRITICAL(&audioRingMux);

    uint32_t available = ringAvailableUnsafe();
    uint32_t n = min(len, available) & ~1u;
    ringTail = (ringTail + n) % audioRingSize;

    portEXIT_CRITICAL(&audioRingMux);
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
  if (buf == nullptr || len == 0) return;

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

  // GROUND TRUTH: if SCO data is flowing during a call, SCO is up.
  if (callActive && !audioConnected)
  {
    audioConnecting    = false;
    audioConnected     = true;
    pendingAudioFormat = true;   // -> audio_format goes to backend
    dbgScoInferred     = true;   // printed later from loop()
  }

  ringWrite(buf, len);

  // Pull one outgoing SCO packet per incoming packet (SCO clock).
  if (audioConnected) esp_hf_client_outgoing_data_ready();
}



uint32_t hfpOutgoingCallback(uint8_t* buf, uint32_t len)
{
    if (!buf || len == 0) return 0;

    // Always supply a complete packet.
    memset(buf, 0, len);

    uint32_t avail = txRingAvailable();
    uint32_t now = millis();

    if (!txPlaying)
    {
        if (avail < txPrebufferBytes())
            return len;

        txPlaying = true;
        aiTtsActive = true;
        aiTtsStartTime = now;
        dbgTtsStarted = true;
    }

    // Temporary shortage: send silence for this packet,
    // but DO NOT reset playback and force another prebuffer.
    if (avail < len)
    {
        txUnderruns++;

        // Finish only after the stream has ended and the ring is empty.
        if (avail == 0 && (now - txLastRxMs) > 800)
        {
            txPlaying = false;
            aiTtsActive = false;
            aiTtsStopTime = now;
            aiConversationTurn++;
        }

        return len;
    }

    uint32_t n = txRingRead(buf, len);

    if (n != len)
    {
        txUnderruns++;
        return len;
    }

    txBytesSent += n;
    aiTtsPlayedBytes += n;

    return len;
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


void recordMicDiagnostics(uint32_t len) {
    uint32_t now = millis();

    micBytes += len;
    micCallbacks++;

    if (micLastCallbackMs != 0) {
        uint32_t gap = now - micLastCallbackMs;
        if (gap > micMaxGapMs) {
            micMaxGapMs = gap;
        }
    }

    micLastCallbackMs = now;

    if (now - micLastReport >= 1000) {
        Serial.printf(
            "[MIC_DIAG] bytes/s=%lu callbacks/s=%lu maxGap=%lu ms\n",
            (unsigned long)micBytes,
            (unsigned long)micCallbacks,
            (unsigned long)micMaxGapMs
        );

        micBytes = 0;
        micCallbacks = 0;
        micMaxGapMs = 0;
        micLastReport = now;
    }
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


void printMemoryDiagnostics() {
    Serial.printf(
        "[MEM] free=%u minFree=%u largestBlock=%u\n",
        (unsigned)ESP.getFreeHeap(),
        (unsigned)ESP.getMinFreeHeap(),
        (unsigned)heap_caps_get_largest_free_block(
            MALLOC_CAP_8BIT
        )
    );
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
    // WiFi nahi hai to WebSocket start mat karo
    if (WiFi.status() != WL_CONNECTED)
        return;

    // IMPORTANT:
    // webSocket.begin() sirf EK BAAR call hoga.
    // Uske baad WebSocketsClient khud reconnect karega.
    if (backendInitialized)
        return;

    if (wsBeginInProgress)
        return;

    unsigned long now = millis();

    // Extra protection against duplicate initialization
    if (lastWsConnectAttempt != 0 &&
        (now - lastWsConnectAttempt) < WS_RECONNECT_GUARD)
    {
        return;
    }

    wsBeginInProgress = true;
    lastWsConnectAttempt = now;

    String websocketPath =
        String(BACKEND_BASE_PATH) +
        String(deviceId);

    Serial.println();
    Serial.println("=================================");
    Serial.println("STARTING BACKEND WEBSOCKET");
    Serial.println("=================================");

    Serial.print("Host: ");
    Serial.println(BACKEND_HOST);

    Serial.print("Port: ");
    Serial.println(BACKEND_PORT);

    Serial.print("Device ID: ");
    Serial.println(deviceId);

    Serial.print("Path: ");
    Serial.println(websocketPath);

    Serial.printf(
        "Free heap before WS: %u\n",
        ESP.getFreeHeap()
    );

    // Register callback BEFORE begin
    webSocket.onEvent(webSocketEvent);

    // Start WebSocket ONLY ONCE
    webSocket.begin(
        BACKEND_HOST,
        BACKEND_PORT,
        websocketPath.c_str(),
        ""
    );

    // Library handles reconnect automatically
    webSocket.setReconnectInterval(2000);

    // Keep connection alive
    webSocket.enableHeartbeat(
        30000,   // ping interval
        15000,   // pong timeout
        3        // reconnect after missed pongs
    );

    backendInitialized = true;
    wsBeginInProgress = false;

    Serial.println("BACKEND WEBSOCKET INITIALIZED");
    Serial.println("Waiting for WS CONNECTED event...");
}

// ============================================================
// WEBSOCKET EVENT
// ============================================================

void printBackendLog(const char* payload, size_t length)
{
  if (payload == nullptr || length == 0) return;

  Serial.println();
  Serial.println("┌────────────────────────────────────────────┐");
  Serial.println("│  📩 RECEIVED DATA FROM THE BACKEND        │");
  Serial.println("├────────────────────────────────────────────┤");
  Serial.printf ("│ Time   : %lu ms\n", millis());
  Serial.printf ("│ Length : %u bytes\n", (unsigned)length);
  Serial.println("├────────────────────────────────────────────┤");
  Serial.print  ("│ Payload: ");
  Serial.println(payload);
  Serial.println("└────────────────────────────────────────────┘");
  Serial.println();
}

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

      Serial.printf(
          "WS connection #%lu\n",
          (unsigned long)wsConnectCount
      );

      Serial.printf(
          "WS generation #%lu\n",
          (unsigned long)wsGeneration
      );

      Serial.printf(
          "Uptime: %lus\n",
          millis() / 1000
      );

      Serial.printf(
          "WiFi RSSI: %d dBm\n",
          WiFi.RSSI()
      );

      Serial.printf(
          "Free heap: %u\n",
          ESP.getFreeHeap()
      );

      char msgBuf[128];

      snprintf(
          msgBuf,
          sizeof(msgBuf),
          "{\"event\":\"device_ready\",\"device_id\":\"%s\"}",
          deviceId
      );

      if (webSocket.sendTXT(msgBuf))
      {
          Serial.println("device_ready SENT");

          logAI(
              "📤",
              "AI-READY",
              "Backend connected - AI is online"
          );
      }
      else
      {
          Serial.println(
              "WARNING: device_ready SEND FAILED"
          );
      }

      break;
  }

  case WStype_DISCONNECTED:
  {
      backendConnected = false;

      wsBeginInProgress = false;
      wsReconnectPending = true;

      wsDisconnectCount++;
      lastWsDisconnect = millis();

      Serial.println();
      printAIActivityBanner("BACKEND DISCONNECTED");

      Serial.printf(
          "Disconnect #%lu\n",
          (unsigned long)wsDisconnectCount
      );

      Serial.printf(
          "WS generation: %lu\n",
          (unsigned long)wsGeneration
      );

      Serial.printf(
          "Uptime: %lus\n",
          millis() / 1000
      );

      Serial.printf(
          "WiFi: %s\n",
          WiFi.status() == WL_CONNECTED
              ? "CONNECTED"
              : "DISCONNECTED"
      );

      if (WiFi.status() == WL_CONNECTED)
      {
          Serial.printf(
              "WiFi RSSI: %d dBm\n",
              WiFi.RSSI()
          );
      }

      Serial.printf(
          "Free heap: %u\n",
          ESP.getFreeHeap()
      );

      Serial.printf(
          "Largest block: %u\n",
          (unsigned)heap_caps_get_largest_free_block(
              MALLOC_CAP_8BIT
          )
      );

      Serial.printf(
          "Min heap: %u\n",
          ESP.getMinFreeHeap()
      );

      Serial.println(
          "WS reconnect requested - "
          "library will handle reconnect"
      );

      // VERY IMPORTANT:
      //
      // DON'T DO THIS:
      //
      // backendInitialized = false;
      // webSocket.begin(...);
      //
      // WebSocketsClient already handles reconnect.

      logAI(
          "⚠️",
          "AI-OFFLINE",
          "Backend disconnected - "
          "AI unavailable until reconnect"
      );

      break;
  }

  case WStype_ERROR:
  {
    Serial.println();
    Serial.println("╔════════════════════════════════════════════╗");
    Serial.println("║   ❌ WEBSOCKET ERROR FROM BACKEND         ║");
    Serial.println("╚════════════════════════════════════════════╝");
    Serial.printf("│ Time    : %lu ms\n", millis());
    Serial.printf("│ Error   : %s\n", payload ? (const char*)payload : "(no payload)");
    Serial.printf("│ WiFi    : %d dBm\n", WiFi.RSSI());
    Serial.printf("│ FreeHeap: %u\n", ESP.getFreeHeap());
    Serial.println("╚════════════════════════════════════════════╝");
    break;
  }

  case WStype_TEXT:
  {
    if (payload != nullptr && length > 0)
    {
      const char* p = (const char*)payload;
      printBackendLog(p, length);

      // ============================================================
      // BACKEND LOG - हर text message यहाँ print होगा
      // ============================================================
      Serial.println();
      Serial.println("╔════════════════════════════════════════════╗");
      Serial.println("║   📩 RECEIVED DATA FROM THE BACKEND        ║");
      Serial.println("╚════════════════════════════════════════════╝");
      Serial.printf("│ Time    : %lu ms\n", millis());
      Serial.printf("│ Length  : %u bytes\n", (unsigned)length);
      Serial.printf("│ Payload : %s\n", p);
      Serial.println("╚════════════════════════════════════════════╝");
      Serial.println();

      // Barge-in: backend ने TTS cancel मांगा है
      if (strstr(p, "ai_audio_cancel"))
      {
        txRingClear();
        aiTtsActive = false;
        Serial.println("🛑 [TTS CANCEL] Backend requested audio buffer clear");
        logAI("🛑", "AI-INTERRUPT", "Backend cancelled TTS (user barge-in or new command)");
        break;
      }

      // Specific event types के लिए extra logs
      if (strstr(p, "\"error\""))
      {
        Serial.println("❌ [BACKEND ERROR]");
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
        Serial.println("📝 [TRANSCRIPT FROM BACKEND]");
        logAI("📝", "AI-HEARD", p);
      }
      else if (strstr(p, "ai_text") || strstr(p, "response_text"))
      {
        Serial.println("💬 [AI RESPONSE TEXT]");
        logAI("💬", "AI-SAID", p);
      }
      else if (strstr(p, "stt") || strstr(p, "speech_to_text"))
      {
        Serial.println("🎤 [STT RESULT]");
        logAI("🎤", "AI-STT", p);
      }
      else if (strstr(p, "tts") || strstr(p, "text_to_speech"))
      {
        Serial.println("🔊 [TTS EVENT]");
        logAI("🔊", "AI-TTS", p);
      }
      else if (strstr(p, "llm") || strstr(p, "response"))
      {
        Serial.println("🤖 [LLM RESPONSE]");
        logAI("🤖", "AI-LLM", p);
      }
      else
      {
        // कोई भी अन्य text message
        Serial.println("📨 [BACKEND MESSAGE - UNKNOWN TYPE]");
        logAI("📨", "AI-BACKEND", p);
      }
    }
    else
    {
      Serial.println();
      Serial.println("⚠️ [BACKEND] Empty TEXT message received");
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

      // AI response tracking
      aiResponseBytes += length;
      aiResponseChunks++;
      aiLastResponseMs = millis();

      // पहला chunk आया तो AI response start log करो
      if (aiResponseChunks == 1)
      {
        Serial.println();
        Serial.println("╔════════════════════════════════════════════╗");
        Serial.println("║   🎵 BINARY AUDIO FROM BACKEND (TTS)      ║");
        Serial.println("╚════════════════════════════════════════════╝");
        logAI("📥", "AI-RESPONSE", "Backend ने AI response (TTS audio) भेजना शुरू किया");
      }
    }

    static uint32_t binCount = 0;
    binCount++;

    // हर 50 chunks पर progress log
    if (binCount % 50 == 0)
    {
      Serial.printf("📦 [AI-TTS] chunk #%lu | ring=%u | played=%lu | drop=%lu | underrun=%lu\n",
                    (unsigned long)binCount,
                    (unsigned)txRingAvailable(),
                    (unsigned long)aiTtsPlayedBytes,
                    (unsigned long)txBytesDropped,
                    (unsigned long)txUnderruns);
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
        Serial.println("SCO AUDIO CONNECTED | Codec: CVSD | 8000 Hz | PCM expected");
        printAIActivityBanner("VOICE CHANNEL OPEN (CVSD 8kHz)");
        logAI("🎤", "AI-LISTEN", "SCO audio connected - AI can now hear you");
        aiListening = true;
        aiUserSpeechBytes = 0;
        aiUserSpeechChunks = 0;
        aiResponseBytes = 0;
        aiResponseChunks = 0;
      }
      // else if (state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTED_MSBC)
      // {
      //   audioConnecting = false;
      //   audioConnected  = true;
      //   audioSampleRate = 16000;
      //   audioCodecName  = "mSBC";
      //   lastCbMs = 0; maxCbGapMs = 0; bigGapCount = 0;
      //   ringClear();
      //   txRingClear();
      //   pendingAudioFormat = true;
      //   Serial.println("SCO AUDIO CONNECTED | Codec: mSBC | 16000 Hz");
      //   Serial.println("⚠️ mSBC/WBS negotiated. This firmware sends raw callback bytes as PCM, so mSBC must be DISABLED in build config.");
      //   Serial.println("   Set CONFIG_BT_HFP_WBS_ENABLE=n, rebuild, erase flash/NVS if needed, then pair again.");
      //   printAIActivityBanner("VOICE CHANNEL OPEN (mSBC - NOT SUPPORTED IN THIS BUILD)");
      //   logAI("🎤", "AI-LISTEN", "SCO audio connected - AI can now hear you");
      //   aiListening = true;
      //   aiUserSpeechBytes = 0;
      //   aiUserSpeechChunks = 0;
      //   aiResponseBytes = 0;
      //   aiResponseChunks = 0;
      // }
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
  if (!slcConnected || !callActive || audioConnected || !remoteDeviceKnown) return;

  unsigned long now = millis();

  // Unstick: if the stack never answered, allow a retry
  if (audioConnecting && now - lastAudioConnectAttempt > 8000)
  {
    audioConnecting = false;
    Serial.println("SCO connect timeout -> retry allowed");
  }
  if (audioConnecting) return;

  if (now - lastAudioConnectAttempt < AUDIO_RECONNECT_INTERVAL) return;

  lastAudioConnectAttempt = now;
  audioConnecting = true;

  Serial.println("\nOPENING SCO AUDIO");
  esp_err_t result = esp_hf_client_connect_audio(remoteDevice);
  Serial.printf("SCO request: %s (%d)\n", result == ESP_OK ? "OK" : "FAILED", (int)result);
  if (result != ESP_OK) audioConnecting = false;
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
// PENDING EVENTS -> BACKEND
// ============================================================
void printDeferredDebug()
{
  if (dbgScoInferred)
  {
    dbgScoInferred = false;
    logAI("🎵", "AI-SCO", "SCO data flowing -> audioConnected inferred, audio_format queued");
  }
  if (dbgTtsStarted)
  {
    dbgTtsStarted = false;
    logAI("🔊", "AI-SPEAK", "TTS playback STARTED");
    Serial.printf("           ring=%u prebuffer=%u\n",
                  (unsigned)txRingAvailable(), (unsigned)txPrebufferBytes());
  }

  static unsigned long lastRx = 0;
  if (audioConnected && millis() - lastRx > 5000)
  {
    lastRx = millis();
    Serial.printf("🎤 [HFP RX] cb=%u rx=%uB micRing=%u\n",
                  (unsigned)audioCallbackCount, (unsigned)audioRxBytes,
                  (unsigned)ringAvailable());
  }
}

// ============================================================
// AUDIO STREAMING -> BACKEND
// ============================================================

void handleAudioStreaming()
{
    if (!backendConnected || !audioConnected) return;

    static uint8_t chunk[AUDIO_SEND_CHUNK];

    for (int i = 0; i < 2; i++) {
        uint32_t avail = ringAvailable() & ~1u;

        if (avail < AUDIO_SEND_MIN) break;

        uint32_t want = min(avail, (uint32_t)AUDIO_SEND_CHUNK);
        uint32_t n = ringPeek(chunk, want);

        n &= ~1u;
        if (n == 0) break;

        // Do not remove audio from the ring until send succeeds.
        if (webSocket.sendBIN(chunk, n)) {
            ringDiscard(n);

            audioSentBytes += n;
            audioSentFrames++;

            aiUserSpeechBytes += n;
            aiUserSpeechChunks++;
            aiLastUserSpeechMs = millis();

            if (aiUserSpeechChunks == 1) {
                Serial.println();
                logAI("🎤", "AI-HEAR",
                      "User is speaking -> streaming to AI...");
            }
        } else {
            Serial.println("[WS AUDIO] sendBIN failed; audio retained");
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

  // IMPORTANT: Route SCO audio through HCI so the registered HFP
  // callbacks receive software audio. This MUST be done before
  // esp_hf_client_init() / before the SCO link is established.
  result = esp_bredr_sco_datapath_set(ESP_SCO_DATA_PATH_HCI);
  Serial.print("SCO datapath = HCI: ");
  Serial.println(result == ESP_OK ? "OK" : "FAILED");
  if (result != ESP_OK)
  {
    Serial.println("ERROR: HCI SCO datapath could not be enabled.");
    return;
  }

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
  Serial.println("AUDIO PATH: HFP Voice-over-HCI + CVSD PCM");
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


String escapeJson(const String& input) {
  String output;
  output.reserve(input.length() + 16);

  for (size_t i = 0; i < input.length(); i++) {
    char c = input[i];

    switch (c) {
      case '\"': output += "\\\""; break;
      case '\\': output += "\\\\"; break;
      case '\n': output += "\\n"; break;
      case '\r': output += "\\r"; break;
      case '\t': output += "\\t"; break;
      default:
        if ((uint8_t)c >= 0x20) output += c;
        break;
    }
  }

  return output;
}

void sendUserTextToBackend(const String& recognizedText) {
  if (!backendConnected || recognizedText.length() == 0) {
    return;
  }

  String payload =
      "{\"event\":\"user_text\",\"text\":\"" +
      escapeJson(recognizedText) + "\"}";

  webSocket.sendTXT(payload);

  Serial.print("TEXT SENT: ");
  Serial.println(recognizedText);
}



void loop()
{
    const uint32_t loopStart = millis();

    uint32_t t = millis();
    if (backendInitialized) {
        webSocket.loop();
    }
    const uint32_t wsMs = millis() - t;

    t = millis();
    handleWiFi();
    connectBackend();
    const uint32_t wifiMs = millis() - t;

    t = millis();
    connectHFP();
    handleAutoAnswer();
    connectSCO();
    const uint32_t btMs = millis() - t;

    t = millis();
    handlePendingEvents();
    const uint32_t eventsMs = millis() - t;

    t = millis();
    handleAudioStreaming();
    const uint32_t audioMs = millis() - t;

    t = millis();
    printDeferredDebug();
    printSystemStatus();
    const uint32_t debugMs = millis() - t;

    const uint32_t totalMs = millis() - loopStart;

    static uint32_t lastReport = 0;
    static uint32_t maxTotal = 0;
    static uint32_t maxWs = 0;
    static uint32_t maxAudio = 0;
    static uint32_t maxBt = 0;

    if (totalMs > maxTotal) maxTotal = totalMs;
    if (wsMs > maxWs) maxWs = wsMs;
    if (audioMs > maxAudio) maxAudio = audioMs;
    if (btMs > maxBt) maxBt = btMs;

    if (millis() - lastReport >= 2000) {
        lastReport = millis();

        Serial.printf(
            "[LOOP DIAG] total=%lu ms | WS=%lu | WiFi=%lu"
            " | BT=%lu | events=%lu | audio=%lu | debug=%lu"
            " | maxTotal=%lu maxWS=%lu maxAudio=%lu maxBT=%lu\n",
            (unsigned long)totalMs,
            (unsigned long)wsMs,
            (unsigned long)wifiMs,
            (unsigned long)btMs,
            (unsigned long)eventsMs,
            (unsigned long)audioMs,
            (unsigned long)debugMs,
            (unsigned long)maxTotal,
            (unsigned long)maxWs,
            (unsigned long)maxAudio,
            (unsigned long)maxBt
        );

        maxTotal = maxWs = maxAudio = maxBt = 0;
    }

    delay(1);
}
