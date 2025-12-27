from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings

API_KEY = "sk_81a58227f843864721833e1b1dee9cbb66312f7234247bbc"
VOICE_ID = "8jHHF8rMqMlg8if2mOUe"

MODEL_ID="eleven_turbo_v2_5" 

def generate_tts(text: str, out_path="output.mp3"):
    client = ElevenLabs(api_key=API_KEY)

   # (voice_id: str, *, text: str, enable_logging: Optional[bool] = None, 
   # optimize_streaming_latency: Optional[int] = None, 
   # output_format: Union[Literal['mp3_22050_32', 'mp3_24000_48', 'mp3_44100_32', 'mp3_44100_64', 'mp3_44100_96', 'mp3_44100_128', 'mp3_44100_192', 'pcm_8000', 'pcm_16000', 'pcm_22050', 'pcm_24000', 'pcm_32000', 'pcm_44100', 'pcm_48000', 'ulaw_8000', 'alaw_8000', 'opus_48000_32', 'opus_48000_64', 'opus_48000_96', 'opus_48000_128', 'opus_48000_192'], Any, NoneType] = None, 
   # model_id: Optional[str] = Ellipsis, 
   # language_code: Optional[str] = Ellipsis, 
   # voice_settings: Optional[elevenlabs.types.voice_settings.VoiceSettings] = Ellipsis, 
   # pronunciation_dictionary_locators: Optional[Sequence[elevenlabs.types.pronunciation_dictionary_version_locator.PronunciationDictionaryVersionLocator]] = Ellipsis, seed: Optional[int] = Ellipsis, previous_text: Optional[str] = Ellipsis, next_text: Optional[str] = Ellipsis,
   # previous_request_ids: Optional[Sequence[str]] = Ellipsis, 
   # next_request_ids: Optional[Sequence[str]] = Ellipsis, 
   # use_pvc_as_ivc: Optional[bool] = Ellipsis, 
   # apply_text_normalization: Union[Literal['auto', 'on', 'off'], Any,
   # NoneType] = Ellipsis, apply_language_text_normalization: Optional[bool] = Ellipsis,
   # request_options: Optional[elevenlabs.core.request_options.RequestOptions] = None) -> Iterator[bytes]
    

    # 
    voice_settings = VoiceSettings(
        stability=0.51,
        similarity_boost=0.78,
        style=0.38,
        use_speaker_boost=True
    )

    audio_stream = client.text_to_speech.convert(
        text=text,
        voice_id=VOICE_ID,
        model_id=MODEL_ID,
        voice_settings=voice_settings,
        
    )

    with open(out_path, "wb") as f:
        for chunk in audio_stream:
            f.write(chunk)

    return out_path


if __name__ == "__main__":
    path = generate_tts("안녕하세요. 오늘 보여드릴 스타일은 블랙 자켓입니다.", out_path="output.mp3")
    print("saved:", path)

