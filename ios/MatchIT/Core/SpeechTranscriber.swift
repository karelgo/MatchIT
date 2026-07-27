import AVFoundation
import Observation
import Speech

/// Live speech-to-text for the voice-first concierge.
///
/// Streams partial results while recording; the caller owns what the text means
/// (here: the problem description being dictated).
@MainActor
@Observable
final class SpeechTranscriber {
    private(set) var isRecording = false
    var errorMessage: String?

    private let engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var onTranscript: ((String) -> Void)?

    func start(onTranscript: @escaping (String) -> Void) {
        guard !isRecording else { return }
        self.onTranscript = onTranscript
        SFSpeechRecognizer.requestAuthorization { status in
            Task { @MainActor [weak self] in
                guard let self else { return }
                guard status == .authorized else {
                    self.errorMessage = "Speech recognition isn't allowed. Enable it in Settings."
                    return
                }
                AVAudioApplication.requestRecordPermission { granted in
                    Task { @MainActor [weak self] in
                        guard let self else { return }
                        guard granted else {
                            self.errorMessage = "Microphone access isn't allowed. Enable it in Settings."
                            return
                        }
                        self.beginRecording()
                    }
                }
            }
        }
    }

    func stop() {
        guard isRecording else { return }
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        task = nil
        request = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func beginRecording() {
        guard let recognizer, recognizer.isAvailable else {
            errorMessage = "Speech recognition isn't available right now."
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            self.request = request

            let input = engine.inputNode
            let format = input.outputFormat(forBus: 0)
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
                request.append(buffer)
            }
            engine.prepare()
            try engine.start()
            isRecording = true
            errorMessage = nil

            task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                // Extract Sendable values before hopping to the main actor —
                // the recognition result itself is not Sendable.
                let text = result?.bestTranscription.formattedString
                let finished = error != nil || (result?.isFinal ?? false)
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    if let text { self.onTranscript?(text) }
                    if finished { self.stop() }
                }
            }
        } catch {
            errorMessage = "Could not start the microphone."
            stop()
        }
    }
}
