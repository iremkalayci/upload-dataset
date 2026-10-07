# UploadDataset

> Selects video frames at a configurable interval and uploads the selected images to a NovaVision dataset through the NovaVision Data API.

**Category:** Auxiliary

**Status:** Stable

**Last Updated:** 07.10.2026

---

## 1. Overview

UploadDataset is a NovaVision component designed to selectively transfer frames received from a VideoFeed pipeline to a NovaVision dataset. Instead of uploading every incoming video frame, the component applies a configurable frame sampling interval, converts selected frames to JPEG format, and uploads them through the NovaVision Data API.

The component uses Redis-based state management to maintain the frame sampling counter and session-level batch information. It supports both manually specified batch names and automatic batch creation through the Data API. Duplicate image responses are handled without interrupting the workflow.

UploadDataset is intended for workflows where video streams need to be converted into a controlled collection of images for dataset creation or enrichment while avoiding unnecessary uploads of every incoming frame.

**Typical use cases:**

- Sampling frames from a VideoFeed and uploading them to a NovaVision object detection dataset.
- Creating datasets from video streams using a configurable sampling frequency.
- Adding selected frames to an existing dataset batch.
- Allowing the Data API to create and manage a batch automatically.
- Integrating video-based image collection into a NovaVision workflow.

---

## 2. Inputs

| Field Name | Kind/Type | Required | Default | Description |
|---|---|---|---|---|
| `inputImage` | `object` | Yes | `—` | Image object received from the VideoFeed pipeline. The component uses the image metadata and retrieves the actual frame through the NovaVision `Image.get_frame` mechanism. |

> Derived from the package `Inputs` / `Input` classes. The `inputImage` field is defined as an object and is expected to contain the information required by the NovaVision runtime to access the corresponding frame.

---

## 3. Configuration Parameters

| Parameter | Type | Field Type (UI control) | Allowed Values / Range | Default | Description |
|---|---|---|---|---|---|
| `configDataset` | `string` | `widget` | `object_detection` datasets | `—` | Selects the target NovaVision dataset where sampled images will be uploaded. |
| `BatchName` | `string` | `textInput` | Any valid batch name or empty | `""` | Specifies the batch to which images are uploaded. If empty, an existing session batch is reused when available; otherwise, the Data API may create a batch automatically. |
| `FrameInterval` | `number` | `textInput` | Integer `>= 1` | `5` | Determines the frame sampling interval. The first received frame is selected, followed by every Nth frame. For example, `5` selects frames `1, 6, 11, 16, ...`. |

### Dataset Configuration

The `configDataset` parameter uses the NovaVision Dataset Picker and is configured for:

~~~text
object_detection
~~~

The selected dataset value is parsed by the component to extract the `id_dataset` required by the NovaVision Data API.

The dataset value can be handled when provided as:

- A JSON string containing `id_dataset`
- A dictionary containing `id_dataset`
- A numeric value
- A numeric string

The parsed dataset ID must be a positive integer.

### Batch Configuration

`BatchName` allows the user to specify an existing batch or a new batch name.

If the field is left empty, the component first checks Redis for an existing batch associated with the current video session. If no batch is available, the Data API can create one automatically and return its name. The returned batch name is then stored in Redis for subsequent uploads in the same session.

### Frame Sampling Configuration

`FrameInterval` determines how frequently incoming frames are selected for upload.

For example:

~~~text
FrameInterval = 5

Frame 1   -> Upload
Frame 2   -> Skip
Frame 3   -> Skip
Frame 4   -> Skip
Frame 5   -> Skip
Frame 6   -> Upload
Frame 7   -> Skip
...
~~~

A lower interval produces more selected frames, while a higher interval reduces the number of uploaded images.

---

## 4. Outputs

| Field Name | Kind/Type | Description |
|---|---|---|
| `outputImage` | `object` | The original input image passed through as the component output. The component performs dataset upload as an additional processing operation and does not replace the workflow image with the uploaded JPEG. |

The component preserves the original workflow image:

~~~python
self.result = self.input_image
~~~

The response is then constructed through `build_response()` using the NovaVision package response structure.

The uploaded JPEG is therefore used for the Data API request only. It is not returned as the workflow output.

---

## 5. Processing Flow

The complete UploadDataset processing flow is:

~~~mermaid
flowchart TD
    A[VideoFeed] --> B[UploadDataset]
    B --> C[Read Input Image and Metadata]
    C --> D[Generate Redis Session Key]
    D --> E[Increment Redis Frame Counter]
    E --> F{Frame Selected?}

    F -- No --> G[Skip Upload]
    G --> H[Return Original Input Image]

    F -- Yes --> I[Parse Dataset ID]
    I --> J[Retrieve Frame with Image.get_frame]
    J --> K[Convert Frame to NumPy Array]
    K --> L[Convert BGR/BGRA to RGB]
    L --> M[Encode as JPEG]
    M --> N[Read API Credentials]
    N --> O[Resolve Batch]
    O --> P[POST /data/image/upload]
    P --> Q{API Response}

    Q -- HTTP 201 --> R[Image Added]
    Q -- HTTP 200 skipped --> S[Duplicate Image]
    Q -- Other Status --> T[Log API Error]

    R --> U[Store Batch in Redis if Needed]
    S --> H
    T --> H
    U --> H
~~~

### Processing Stages

1. VideoFeed provides an image object.
2. UploadDataset reads the image metadata.
3. A session-specific Redis key is generated.
4. The Redis frame counter is incremented.
5. The configured `FrameInterval` determines whether the current frame is selected.
6. Non-selected frames are skipped without an API request.
7. Selected frames are retrieved through `Image.get_frame`.
8. The frame is converted into a NumPy array.
9. BGR/BGRA channel ordering is converted to RGB.
10. The image is encoded as JPEG with quality `95`.
11. API credentials and the API base URL are resolved.
12. The current batch is determined.
13. The JPEG image is uploaded through the NovaVision Data API.
14. Successful and duplicate responses are handled separately.
15. Newly created batch information can be stored in Redis.
16. The original input image is returned through `outputImage`.

---

## 6. Use Case Examples

### Use case 1: Upload sampled VideoFeed frames to a dataset

A VideoFeed component provides image frames to UploadDataset.

~~~text
VideoFeed
    |
    v
UploadDataset
    |
    +--> Frame Sampling
    |
    +--> JPEG Conversion
    |
    +--> NovaVision Data API
              |
              v
        Object Detection Dataset
~~~

UploadDataset receives frames from VideoFeed and evaluates each frame against the configured `FrameInterval`.

For example, with:

~~~text
FrameInterval = 30
~~~

the component selects approximately every 30th incoming frame.

The selected frame is retrieved through the NovaVision runtime, converted to JPEG, and uploaded to the configured dataset.

The original input image is still returned as `outputImage`, allowing the workflow to continue normally.

### Use case 2: Add sampled frames to a specific batch

UploadDataset can be configured with an explicit batch name.

Example configuration:

~~~text
Dataset:
    Traffic Detection Dataset

Batch Name:
    traffic_batch_01

FrameInterval:
    30
~~~

The processing flow is:

~~~text
VideoFeed
    |
    v
UploadDataset
    |
    +--> Sample frames
    |
    +--> Upload selected frames
              |
              v
       traffic_batch_01
~~~

This is useful when frames collected from a specific video, recording session, or experiment need to be grouped under a known dataset batch.

### Use case 3: Automatic batch creation and reuse

If `BatchName` is left empty, UploadDataset can use the batch information returned by the Data API.

The process is:

~~~text
VideoFeed
    |
    v
UploadDataset
    |
    +--> Frame selected
    |
    +--> Data API
          |
          +--> Batch created
          |
          +--> batch_name returned
                    |
                    v
                  Redis
                    |
                    v
          Reused for subsequent uploads
~~~

When the API creates a new batch, the returned `batch_name` is stored in Redis under the current session. Subsequent selected frames can therefore continue using the same batch.

### Use case 4: Duplicate image handling

The NovaVision Data API may return an HTTP `200` response with a `skipped` value when an image is already present.

UploadDataset handles this as an expected duplicate condition rather than a runtime failure.

Example runtime log:

~~~text
HTTP 200 ATLANDI (zaten var)
~~~

This allows the component to continue processing subsequent frames without treating duplicate images as fatal errors.

---

## 7. Limitations and Notes

- `FrameInterval` must be an integer greater than or equal to `1`.
- The default `FrameInterval` is `5`.
- The Dataset Picker is configured for `object_detection` datasets.
- The input frame must be accessible through the NovaVision runtime and `Image.get_frame`.
- Selected frames are converted to JPEG before upload.
- JPEG quality is configured to `95`.
- A valid `DEVICE_ACCESS_TOKEN` is required for authenticated Data API requests.
- The Data API base URL is obtained from the `WEB_API` environment variable.
- Test and production API fallback URLs are defined in the API client.
- `NOVAVISION_WORKSPACE_ID` is optional. The `X-Workspace-Id` header is only added when the value is available.
- Redis is required for frame sampling state and session-level batch information.
- Sampling state is stored using a Redis key derived from the video source metadata and loop information.
- Redis state uses a 24-hour TTL.
- The automatically created batch name also uses the session Redis state and a 24-hour TTL.
- The component does not store or persist the source video.
- VideoFeed is responsible for delivering frames. UploadDataset processes the frames it receives and does not control VideoFeed's end-of-file or restart behavior.
- Duplicate images may result in an HTTP `200` response with `skipped=true`. This is handled as an expected API response rather than a fatal error.
- Unexpected API responses are logged together with their HTTP status and response body.
- Local processing errors are logged and do not intentionally terminate the entire component because of a single frame.
- The component returns the original input image as `outputImage`.
- The JPEG generated for the Data API is used only for the upload operation and is not returned as the workflow output.

---

## 8. Data API Integration

UploadDataset communicates with the NovaVision Data API using:

~~~text
POST /api/data/image/upload
~~~

The request uses Bearer authentication:

~~~text
Authorization: Bearer <DEVICE_ACCESS_TOKEN>
~~~

The multipart request contains the target dataset identifier, optional batch name, and selected JPEG image.

The request structure is conceptually:

~~~text
id_dataset
batch_name
file
~~~

The uploaded file is sent as:

~~~text
filename: frame.jpg
content-type: image/jpeg
~~~

The API client uses:

~~~text
Connection timeout: 5 seconds
Read timeout:       30 seconds
JPEG quality:       95
~~~

The API base URL is resolved using the following logic:

1. Read `WEB_API` from the environment.
2. If `WEB_API` is not available, use the production URL when the runtime environment is `production` or `prod`.
3. Otherwise, use the test URL.

---

## 9. Internal Processing Flow

The component follows the following processing sequence:

1. Receive `inputImage` from the workflow.
2. Read `configDataset`, `BatchName`, and `FrameInterval`.
3. Extract metadata from the incoming image.
4. Generate a Redis session key using the video source metadata and loop information.
5. Increment the Redis frame counter.
6. Apply the configured frame sampling interval.
7. If the frame is not selected, skip the upload operation.
8. Parse the selected dataset ID.
9. Retrieve the selected frame through `Image.get_frame`.
10. Convert the frame to JPEG bytes.
11. Read `DEVICE_ACCESS_TOKEN`, workspace information, and API base URL.
12. Resolve the current batch.
13. Send the JPEG image to the NovaVision Data API.
14. Process the API response.
15. Store a newly created batch name in Redis when applicable.
16. Return the original input image through the standard NovaVision response structure.

---

## 10. Redis State Management

Redis is used to maintain state between individual component executions.

The Redis session key is generated from:

~~~text
video_path or source
+
loop information
~~~

The resulting string is hashed using MD5:

~~~python
raw = (
    f"{meta.get('video_path') or meta.get('source') or ''}"
    f"|{meta.get('loop', 0)}"
)

session = hashlib.md5(raw.encode()).hexdigest()[:12]

key = f"UploadDataset:{session}"
~~~

The resulting Redis key has the following structure:

~~~text
UploadDataset:<session_hash>
~~~

The associated batch value is stored under:

~~~text
UploadDataset:<session_hash>:batch
~~~

Both the sampling state and automatically stored batch information use a 24-hour TTL.

This prevents stale state from remaining indefinitely while preserving the required state during normal video processing.

---

## 11. Frame Sampling Implementation

The sampling counter is incremented in Redis:

~~~python
n = redis.incr(key)
redis.expire(key, TTL)
~~~

The selection condition is:

~~~python
if (n - 1) % self.frame_interval:
    return
~~~

This means that the first received frame is selected and subsequent frames are selected according to the configured interval.

For example:

| Frame Interval | Selected Frames |
|---|---|
| `1` | `1, 2, 3, 4, 5, ...` |
| `5` | `1, 6, 11, 16, 21, ...` |
| `30` | `1, 31, 61, 91, 121, ...` |
| `60` | `1, 61, 121, 181, 241, ...` |

For a 10-minute video running at approximately 30 FPS:

~~~text
10 minutes
x 60 seconds
x 30 FPS
≈ 18,000 input frames
~~~

With:

~~~text
FrameInterval = 30
~~~

the theoretical number of selected frames is approximately:

~~~text
18,000 / 30
≈ 600 selected frames
~~~

The actual number depends on the frame rate and the number of frames delivered by VideoFeed.

---

## 12. Frame Retrieval and JPEG Conversion

Once a frame is selected, the component retrieves the actual frame using the NovaVision SDK:

~~~python
frame = Image.get_frame(
    img=dict(source),
    redis_db=self.redis_db,
)
~~~

A copy of the source dictionary is passed to `Image.get_frame` because the SDK method may modify the supplied dictionary.

The retrieved frame is then converted to a NumPy array:

~~~python
arr = np.asarray(frame).astype(np.uint8)
~~~

For three-channel images, the implementation converts BGR/BGRA channel ordering to RGB:

~~~python
arr = arr[..., 2::-1]
~~~

The resulting array is encoded using Pillow:

~~~python
PILImage.fromarray(arr).save(
    buf,
    format="JPEG",
    quality=JPEG_QUALITY,
)
~~~

The final image is stored in memory as JPEG bytes and passed directly to the Data API request.

---

## 13. Dataset ID Parsing

The Dataset Picker value is converted into the `id_dataset` required by the Data API.

The component supports the following input representations:

~~~text
JSON string
Dictionary
Integer
Numeric string
~~~

For a JSON value such as:

~~~json
{
    "id_dataset": 7,
    "name": "Traffic Dataset"
}
~~~

the component extracts:

~~~text
id_dataset = 7
~~~

The final value is converted to an integer.

Dataset IDs less than or equal to zero are rejected.

---

## 14. Batch Management

Batch management supports both explicit and automatic batch assignment.

When the user provides a batch name:

~~~text
BatchName = traffic_batch_01
~~~

the configured value is used directly.

When the field is empty, the component first checks Redis:

~~~python
batch = self.batch_name or redis.get(key + ":batch")
~~~

If no batch is available, the API request is sent without `batch_name`, allowing the API to create a batch automatically.

When the API returns a new batch name after a successful non-duplicate upload, the value is stored in Redis:

~~~python
if not skipped and name and not self.batch_name:
    redis.set(
        key + ":batch",
        name,
        ex=TTL,
    )
~~~

This allows subsequent uploads in the same session to reuse the automatically created batch.

---

## 15. Duplicate Handling

The NovaVision Data API can return a successful response indicating that the image already exists.

The component checks the `skipped` value in the response.

| API Response | Component Behavior |
|---|---|
| `HTTP 201` with `skipped=false` | Image is considered successfully added. |
| `HTTP 200` with `skipped=true` | Image is considered a duplicate and is skipped without raising an error. |
| Other HTTP status | Response is logged as an error. |

Example runtime output:

~~~text
HTTP 200 ATLANDI (zaten var)
~~~

This behavior allows the pipeline to continue processing without stopping because of duplicate images.

---

## 16. Authentication and Environment Configuration

The API client reads credentials from the runtime environment.

The primary variables are:

~~~text
WEB_API
DEVICE_ACCESS_TOKEN
NOVAVISION_WORKSPACE_ID
~~~

`WEB_API` defines the Data API base URL.

`DEVICE_ACCESS_TOKEN` is used for Bearer authentication:

~~~text
Authorization: Bearer <DEVICE_ACCESS_TOKEN>
~~~

`NOVAVISION_WORKSPACE_ID` is optional. If it is provided, the client adds:

~~~text
X-Workspace-Id: <workspace_id>
~~~

to the request headers.

The implementation uses the existing runtime-provided `DEVICE_ACCESS_TOKEN` rather than requiring a separate API token variable.

---

## 17. Error Handling

UploadDataset handles local and API-related failures at several stages.

### Dataset Parsing Errors

If the dataset ID cannot be extracted or converted to a valid positive integer, the current upload is skipped and the error is logged.

### Frame Retrieval Errors

If `Image.get_frame` does not return a valid frame, the component logs the problem and skips the current upload.

### JPEG Conversion Errors

Exceptions raised during NumPy or Pillow processing are caught and logged.

### Missing Authentication

If `DEVICE_ACCESS_TOKEN` is unavailable, the API request is not attempted.

### API Errors

Unexpected HTTP responses are logged with both status code and response body.

### Runtime Exceptions

The main `run()` method contains an exception boundary:

~~~python
try:
    self._upload_if_selected()
except Exception as e:
    log(f"HATA ({type(e).__name__}): {e}")
~~~

This prevents an exception associated with a single frame from intentionally terminating the complete component flow.

---

## 18. Runtime Logging

The component uses a dedicated logging helper:

~~~python
def log(*msg):
    print(f"[UploadDataset {VERSION}] {msg}", flush=True)
~~~

The logs include information useful for debugging and runtime verification, including:

- Local frame counter
- VideoFeed source frame index
- Sampling interval
- Dataset ID
- API address
- Workspace information
- Batch name
- JPEG size
- JPEG MD5 prefix
- HTTP status
- Duplicate status
- Batch creation status
- Local processing errors

Example:

~~~text
[UploadDataset v4] kare=101 yükleniyor:
video_kare=100
md5=2ddf7006
dataset=7
batch='denemebatch'
boyut=609505B
~~~

---

## 19. Testing

The component was tested in the NovaVision runtime using VideoFeed as the input source and a NovaVision dataset as the upload target.

The final testing covered:

- Package initialization
- PackageModel configuration
- Executor execution
- Frame sampling
- Redis state management
- Frame retrieval
- JPEG conversion
- Data API authentication
- Dataset upload
- Batch management
- Duplicate handling
- Long-duration video processing
- Runtime error handling

### Frame Sampling Test

With:

~~~text
FrameInterval = 5
~~~

the runtime produced selected frame counters such as:

~~~text
kare=96
kare=101
kare=106
kare=111
kare=116
kare=121
...
~~~

The corresponding VideoFeed frame indices were:

~~~text
video_kare=95
video_kare=100
video_kare=105
video_kare=110
video_kare=115
video_kare=120
...
~~~

This confirmed that the configured sampling interval was being applied consistently.

### API Upload Test

Successful uploads returned the expected successful API response and were logged as:

~~~text
HTTP 201 EKLENDI
~~~

Duplicate images returned:

~~~text
HTTP 200 ATLANDI (zaten var)
~~~

Both behaviors were handled correctly by the component.

### Image Payload Test

Different selected frames produced different JPEG MD5 prefixes, including examples such as:

~~~text
b8e606eb
2ddf7006
e3c4acac
632e4468
2acc5aee
~~~

This confirmed that different source frames were being converted into different JPEG payloads before upload.

### Long Video Test

A longer video was used to verify that the sampling and upload process remained stable across an extended input.

The component continued processing incoming frames according to the configured sampling interval and correctly handled API responses throughout the test.

---

## 20. VideoFeed End-of-File Behavior

During testing, VideoFeed produced runtime messages indicating that the source video reached the end of the file and was subsequently restarted.

This behavior belongs to VideoFeed rather than UploadDataset.

UploadDataset does not store the source video and does not control whether VideoFeed stops or restarts after EOF. It processes only the image frames delivered to it.

Therefore, VideoFeed restart behavior does not require additional video persistence logic inside UploadDataset.

---

## 21. Development Status

The component has been implemented and tested end-to-end in the NovaVision runtime.

Completed implementation areas include:

- Package initialization
- PackageModel design
- Executor implementation
- Configurable frame sampling
- Redis-based state management
- Frame retrieval
- JPEG conversion
- NovaVision Data API integration
- Dataset selection
- Batch management
- Duplicate response handling
- Runtime error handling
- End-to-end VideoFeed testing
- Technical documentation

The component is currently classified as **Stable** because the core functionality has been implemented and verified through end-to-end runtime testing with VideoFeed and the NovaVision Data API.

---

## 22. Technical Summary

| Feature | Implementation |
|---|---|
| Component | `UploadDataset` |
| Input source | NovaVision VideoFeed |
| Input type | `object` |
| Dataset type | `object_detection` |
| Frame sampling | Configurable N-frame interval |
| Default interval | `5` |
| Minimum interval | `1` |
| State management | Redis |
| State TTL | 24 hours |
| Frame retrieval | `Image.get_frame()` |
| Image processing | NumPy + Pillow |
| Output upload format | JPEG |
| JPEG quality | `95` |
| Authentication | Bearer token via `DEVICE_ACCESS_TOKEN` |
| API base URL | `WEB_API` |
| Upload endpoint | `/data/image/upload` |
| Dataset parameter | `id_dataset` |
| Image parameter | `file` |
| Batch parameter | `batch_name` |
| Batch management | Manual or API-created |
| Duplicate handling | HTTP `200` with `skipped` |
| Workflow output | Original input image |
| Runtime resilience | Per-frame exception handling |
| Test status | End-to-end tested |
| Current status | Stable |