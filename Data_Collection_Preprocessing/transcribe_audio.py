import io
import os
import sys
import configparser
import time
import wave
from pydub import AudioSegment
from moviepy.editor import *
from datetime import datetime, timedelta
# Imports the Google Cloud client library
from google.cloud import storage, speech, speech_v1
# from google.cloud.speech import enums, types
# from google.cloud.speech_v1 import types
from pydub.effects import normalize
from pydub.silence import split_on_silence
from pydub.utils import mediainfo


class Transcribe:
    """
    Class with the different functions used to transcribe all the audio files to text using google speech to text API.
    The result of th transcription are saved in a text file.
    """
    config = configparser.ConfigParser()
    config.read('gcloud.ini')
    bucket_name = config['CREDENTIALS']['BUCKET_NAME']
    jsonfile = config['CREDENTIALS']['JSON']

    supported = ["wav", "mp3", "ogg", "flac", "mpeg", "mp4"]  # list of files extension accepted by google STT API

    def __init__(self, audiofile):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.jsonfile

        self.audiofile = audiofile
        self.audioext = os.path.splitext(self.audiofile)[1]
        # print("Extension 1 = ", self.audioext)
        self.audioext = self.audioext.split(".")[1]
        # print("Extension 2 = ", self.audioext)

        self.wavfile = os.path.basename(self.audiofile) + ".wav"
        self.transcriptfile = f"transcript/{os.path.basename(self.audiofile)}.txt"

        if not os.path.isdir("transcript"):
            os.mkdir("transcript")
        self.frames = None
        self.frame_rate = None
        self.channels = None
        self.duration = None
        self.blob = None
        if not self.audioext in self.supported:
            raise Exception(f"Unknown Ext: {self.audioext}")
        self.toWav()
        # self.sliceOnSilent()

    # def sliceOnSilent(self):
    #     """
    #     Slip an audio file containing more than one reported voice phishing
    #     phone call. Split audio according with more than 10 seconds of silence
    #     :return:
    #     """
    #
    #     # open the file
    #     sound = AudioSegment.from_file(self.audiofile)
    #     # print(sound)
    #
    #     # Split track where the silence is 2 seconds or more and get chunks using
    #     # the imported function.
    #     print(f"Starting chunking {sound}")
    #     chunks = split_on_silence(
    #         sound,
    #         # Specify that a silent chunk must be at least 10 seconds or 10000 ms long.
    #         min_silence_len=2000,
    #         # # Consider a chunk silent if it's quieter than -16 dBFS.
    #         silence_thresh=-16
    #     )
    #     print(f"chunking completed")
    #     # print(chunks)
    #
    #     # Process each chunk by adding silent padding before and after the chunk
    #     for i, chunk in enumerate(chunks):
    #         # Create a silence chunk that's 0.5 seconds (or 500 ms) long for padding.
    #         silence_chunk = AudioSegment.silent(duration=500)
    #
    #         # Add the padding chunk to beginning and end of the entire chunk.
    #         audio_chunk = silence_chunk + chunk + silence_chunk
    #         audio_chunk = audio_chunk.set_channels(1)
    #         # Export the audio chunk with new bitrate.
    #         print("Exporting chunk{0}.wav from".format(i))
    #         # audio_chunk.export("audio/", self, format="wav")
    #         audio_chunk.export("./chunk{0}.wav".format(i), format="wav", bitrate="16k")

    def match_target_amplitude(sound, target_dbfs=-20):
        change_in_dbfs = target_dbfs - sound.dBFS
        return sound.apply_gain(change_in_dbfs)

    def toWav(self):
        """
        Convert the input file video or audio file into a lossless encoding (FLAC or LINEAR16)
        :return:
        """
        # original_bitrate = mediainfo(self.audiofile)['bit_rate']
        # print('Original bitrate is {} and sample rate is {}'.format(original_bitrate,
        #                                                             mediainfo(self.audiofile)['sample_rate']))
        sound = AudioSegment.from_file(self.audiofile)

        if not os.path.isfile(self.wavfile):
            if self.audioext == "mp4" or self.audioext == "mpeg":
                # convert the video to audio
                videoclip = VideoFileClip(self.audiofile)
                audioclip = videoclip.audio
                audioclip.write_audiofile(self.wavfile)
                audioclip.close()
                videoclip.close()
                # setting the  save file to mono
                # print(self.wavfile)
                sound = AudioSegment.from_wav(self.wavfile)
                newsound = sound.set_channels(1)
                # print(f'{self.wavfile} Audio set to mono file.')
                newsound = newsound.set_frame_rate(16000)   # setting the audio sample rate to optimal value for STT API
                newsound.export(self.wavfile, bitrate="16k", format="wav")
            elif self.audioext != "mp4" or self.audioext != "mpeg":
                if self.audioext == "wav":
                    sound = AudioSegment.from_wav(self.audiofile)
                elif self.audioext == "mp3":
                    sound = AudioSegment.from_file(self.audiofile)
                elif self.audioext == "ogg":
                    sound = AudioSegment.from_ogg(self.audiofile)
                elif self.audioext == "flac":
                    sound = AudioSegment.from_flac(self.audiofile)
                    # elif self.audioext == "mpeg":
                    #     sound = AudioSegment.from_file(self.audiofile)
                    # print(f"number of chanel:{sound.channels}")

                newsound = sound.set_channels(1)
                newsound = newsound.set_frame_rate(16000)   # setting the audio sample rate to optimal value for STT API
                newsound.export(self.wavfile, bitrate="16k", format="wav")

                # newsound = normalize(newsound)
                # newsound = self.match_target_amplitude(newsound)
                # change_in_dbfs = (-20) - newsound.dBFS
                # newsound = newsound.apply_gain(change_in_dbfs)
                # newsound = newsound + 5    # uncomment to increase the volume of the file before transcribe it

                # print("duration = ", newsound.duration_seconds)
                # newsound.export(self.wavfile, bitrate="16k", format="wav")
                # print("{} converted to {}".format(self.audiofile, self.wavfile))

        # checking the details of the converted file
        with wave.open(self.wavfile, "rb") as wave_file:
            self.frames = wave_file.getnframes()
            # print(f"frame: {self.frames}")
            self.frame_rate = wave_file.getframerate()
            # print(f"frame_rate: {self.frame_rate}")
            self.channels = wave_file.getnchannels()
            # print(f"channels: {self.channels}")
            self.duration = self.frames / float(self.frame_rate)
            # print(f"duration: {self.duration}")

            if not 1 == self.channels:
                print('The file {} has more than 1 channel'.format(self.wavfile))
                # raise Exception("There can only be one channel in wav file")

        # print("final bitrate is {} and sample rate is {}".format(mediainfo(self.wavfile)['bit_rate'],
        #                                                          mediainfo(self.wavfile)['sample_rate']))
        # print("*" * 100)

    def uploadBlob(self):
        """
        Uploads a file to the  Google bucket.
        :return:
        """
        # self.destination_name = self.wavfile
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket_name)
        self.blob = bucket.blob(self.wavfile)
        self.blob.upload_from_filename(self.wavfile)
        # print("File {} uploaded to the bucket!".format(self.wavfile))
        print("*" * 100)

    def deleteBlob(self):
        """
        Deletes a file from the bucket.
        :return:
        """
        if self.blob:
            self.blob.delete()
            # print("File deleted from bucket")

    def deleteFile(self):
        """
        Deletes a file from the audio folder
        :return:
        """
        os.remove(self.audiofile)
        # print("File {} deleted from audio folder.".format(self.audiofile))
        # os.unlink(self.wavfile)

    def transcribeAudio(self):
        """
        Send a request to the STT API and return the transcript and the accuracy.
        """
        # self.response = None

        response = ''

        # Instantiates a client
        """To use a different version of the API """
        client = speech.SpeechClient()
        # client = speech_v1.SpeechClient()

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,  # if file is FLAC or WAV this line isn't needed
            # sample_rate_hertz=self.frame_rate,
            sample_rate_hertz=16000,  # This value can be optimal for a better transcription result
            language_code="ko-KR",
            enable_automatic_punctuation=True,
            use_enhanced=True,
            # enableSpokenPunctuation=True,
            # model="phone_call", # this feature is not yet available fo the Korean language
            # adaptation=speech_adaptation,
        )

        start = time.time()
        # if the audio file if the file is longer than 1 minutes upload it
        # and use long transcript request
        if self.duration > 59:
            # upload the audio file to google cloud storage for long recognition
            self.uploadBlob()
            gcs_uri = f"gs://{self.bucket_name}/{self.wavfile}"
            # print(f"Transcription of {gcs_uri}")
            audio = speech.RecognitionAudio(uri=gcs_uri)

            # Asynchronously transcribes the audio file specified by the gcs_uri
            operation = client.long_running_recognize(config=config, audio=audio)
            # print("Waiting for Asynchronous transcription to complete...")
            response = operation.result(timeout=10000)
        elif self.duration <= 59:
            # print(f"Transcription of {self.wavfile}")
            with io.open(self.wavfile, "rb") as audio_file:
                content = audio_file.read()
            # audio = {"content": content}
            audio = speech.RecognitionAudio(content=content)
            # print("Waiting for Synchronous transcription to complete...")
            # Detects speech in the audio file
            response = client.recognize(config=config, audio=audio)

        delta_t = time.time() - start
        print("Transcription Time :", str(timedelta(seconds=delta_t)))  # provide time in hour
        # print(response)

        transcript = ""
        for result in response.results:
            transcript += "Confidence: " + str(result.alternatives[0].confidence) + " "
            transcript += result.alternatives[0].transcript + "\n"

        # print(transcript)
        # utf-8 is used to properly encore and write the korean charactere in the file
        f = open(self.transcriptfile, "w", encoding='utf-8')
        f.writelines(transcript)
        f.close()
        print('Transcript file saved!')


def main(audiofile):
    t = Transcribe(audiofile)
    t.uploadBlob()
    t.transcribeAudio()
    t.deleteBlob()
    t.deleteFile()


if __name__ == "__main__":
    # if len(sys.argv) >= 2:
    #     audiofile = sys.argv[1]
    # else:
    #     audiofile = "audio\magic-mono.mp3"
    #
    # main(audiofile)

    filepath = "audio"

    for audiofile in os.listdir(filepath):
        audiofile = os.path.join(filepath, audiofile)
        print("Processing file >> {}".format(audiofile))

        main(audiofile)
        print("*" * 100)