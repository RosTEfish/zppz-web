using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using System;

public class AudioTimeProvider : MonoBehaviour
{
    public const float RecordIntroDelaySeconds = 5f;

    public float AudioTime = 0f; //notes get this value

    float startTime;
    float speed;
    public bool isStart = false;
    public bool isRecordMode = false;
    public float playStartTime = 0f;
    public float audioOffset = 0f;
    public AudioSource bgm;
    public SoundEffect SE;
    public SettingsManager settings;

    private bool bgmStarted;
    private Action onChartAudioStarted;

    public void SetStartTime(float _playStartTime, float _speed, bool recordMode = false, Action chartAudioStarted = null)
    {
        speed = _speed;
        isRecordMode = recordMode;
        onChartAudioStarted = chartAudioStarted;
        bgmStarted = false;
        bgm.pitch = speed;

        if (recordMode)
        {
            // Mirror desktop isRecord: AudioTime begins introDelay before chart time zero.
            playStartTime = _playStartTime - RecordIntroDelaySeconds;
            AudioTime = playStartTime;
            SE.generateSoundEffectList(playStartTime, isOpIncluded: true);
            if (bgm.isPlaying) bgm.Stop();
            startTime = Time.realtimeSinceStartup;
            isStart = true;
            return;
        }

        playStartTime = _playStartTime;
        AudioTime = playStartTime;
        SE.generateSoundEffectList(playStartTime, isOpIncluded: false);
        bgm.time = Mathf.Max(0f, AudioTime);
        bgm.Play();
        bgmStarted = true;
        startTime = Time.realtimeSinceStartup;
        isStart = true;
        onChartAudioStarted?.Invoke();
    }

    public void Pause()
    {
        isStart = false;
        bgm.Stop();
    }

    public void Resume()
    {
        startTime = Time.realtimeSinceStartup;
        playStartTime = AudioTime;
        isStart = true;
        if (AudioTime >= 0f)
        {
            bgm.time = AudioTime;
            bgm.Play();
            bgmStarted = true;
        }
    }

    public void ResetStartTime()
    {
        isStart = false;
        isRecordMode = false;
        bgmStarted = false;
        onChartAudioStarted = null;
        AudioTime = playStartTime;
        bgm.Stop();
    }

    void Update()
    {
        if (!isStart) return;

        audioOffset = settings.offset;

        if (isRecordMode && !bgmStarted)
        {
            AudioTime = (Time.realtimeSinceStartup - startTime) + playStartTime;
            if (AudioTime < 0f) return;

            bgm.time = Mathf.Max(0f, AudioTime);
            bgm.Play();
            bgmStarted = true;
            // Re-anchor so AudioTime stays continuous after BGM starts.
            playStartTime = AudioTime;
            startTime = Time.realtimeSinceStartup;
            onChartAudioStarted?.Invoke();
        }

        if (speed != 1 && bgmStarted)
            AudioTime = bgm.time;
        else
            AudioTime = (Time.realtimeSinceStartup - startTime) + playStartTime;

        if (!bgmStarted) return;

        var delta = AudioTime - bgm.time;
        if (AudioTime >= 0 && Mathf.Abs(delta) > 0.03)
        {
            if (bgm.clip != null && AudioTime > bgm.clip.length)
            {
                bgm.Stop();
                isStart = false;
            }
            if (AudioTime > bgm.time)
                startTime += Mathf.Abs(delta) * 0.7f;
            else
                startTime -= Mathf.Abs(delta) * 0.7f;
        }
    }

    private void FixedUpdate()
    {
        if (isStart)
        {
            SE.SoundEffectUpdate(audioOffset);
        }
    }
}
