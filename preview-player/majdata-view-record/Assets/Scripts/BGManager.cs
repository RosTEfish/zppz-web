using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Video;
using System.IO;
using System.Drawing;
using UnityEngine.UI;
using UnityEngine.UIElements;
using TMPro;

public class BGManager : MonoBehaviour
{
    public static SpriteRenderer spriteRender;
    SpriteRenderer BackgroundCover;
    public SettingsManager settings;
    public VideoPlayer videoPlayer;
    public AudioTimeProvider audioTimeProvider;
    public GameObject videoTarget;
    public bool isAnyErr = false;
    float desireSpeed = 1f;

    private bool showIdleVideoFrame = false;
    private bool lastHideStaticBackground = false;
    private GameObject coversRoot;
    private Animator songDetailAnimator;
    private RawImage jacketImage;
    private TMP_Text titleText;
    private TMP_Text artistText;
    private TMP_Text desText;
    private TMP_Text idText;
    private bool songDetailBound;

    // Scene object named "Covers" is the letterbox vignette. SongDetail lives on
    // Assets/Resources/SongCover/Covers.prefab and is instantiated at runtime.
    private const string SongCoverRootName = "SongCoverUI";
    private const string SongCoverResource = "SongCover/Covers";
    private const string SongCoverAnimatorResource = "SongCover/Animation/Canvas";
    // Prefab SongDetail is authored at ~47×75 (world-space). For Screen Space
    // Overlay, scale the root so the card is about 42% of a 1080p-tall frame.
    private const float SongDetailPrefabHeight = 75f;
    private const float SongCoverTargetHeightFraction = 0.42f;
    private const float SongCoverMinScale = 4f;
    private const float SongCoverMaxScale = 10f;

    void Start()
    {
        spriteRender = GetComponent<SpriteRenderer>();
        BackgroundCover = GameObject.Find("BackgroundCover").GetComponent<SpriteRenderer>();
        audioTimeProvider = GameObject.Find("AudioTimeProvider").GetComponent<AudioTimeProvider>();
        videoPlayer.errorReceived += VideoPlayer_errorReceived;
        SetNewSpriteForVideo();
        BindSongDetail();
    }

    void BindSongDetail()
    {
        if (songDetailBound) return;

        coversRoot = ResolveSongCoverRoot();
        if (coversRoot == null)
        {
            Debug.LogWarning("[MJV][BGManager] SongCoverUI missing; SongDetail intro disabled");
            return;
        }

        var songDetail = coversRoot.transform.Find("SongDetail");
        if (songDetail == null)
        {
            Debug.LogWarning("[MJV][BGManager] SongDetail child missing under SongCoverUI");
            return;
        }

        EnsureSongCoverOverlay(songDetail);
        EnsureSongDetailAnimator();

        var jacket = songDetail.Find("Jacket");
        if (jacket != null) jacketImage = jacket.GetComponent<RawImage>();
        var wrapper = songDetail.Find("TextWrapper");
        if (wrapper != null)
        {
            titleText = wrapper.Find("TitleText")?.GetComponent<TMP_Text>();
            artistText = wrapper.Find("ArtistText")?.GetComponent<TMP_Text>();
            desText = wrapper.Find("DesText")?.GetComponent<TMP_Text>();
            idText = wrapper.Find("IdText")?.GetComponent<TMP_Text>();
        }
        songDetailBound = true;
        coversRoot.SetActive(false);
        Debug.Log("[MJV][BGManager] SongCoverUI bound jacket=" + (jacketImage != null));
    }

    GameObject ResolveSongCoverRoot()
    {
        var existing = GameObject.Find(SongCoverRootName);
        if (existing != null) return existing;

        // Prefer a Covers object that actually owns SongDetail (not the vignette).
        var transforms = FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        foreach (var transform in transforms)
        {
            if (transform.name != "SongDetail") continue;
            var parent = transform.parent;
            if (parent == null || parent.name != "Covers") continue;
            parent.gameObject.name = SongCoverRootName;
            return parent.gameObject;
        }

        var prefab = Resources.Load<GameObject>(SongCoverResource);
        if (prefab == null)
        {
            Debug.LogWarning("[MJV][BGManager] Resources.Load failed for " + SongCoverResource);
            return null;
        }

        // Do not parent under the scene UI Canvas: prefab root is a plain Transform
        // and SongDetail is authored for a separate overlay / world-space setup.
        var instance = Instantiate(prefab);
        instance.name = SongCoverRootName;
        return instance;
    }

    void EnsureSongCoverOverlay(Transform songDetail)
    {
        if (coversRoot == null || songDetail == null) return;

        var canvas = coversRoot.GetComponent<Canvas>();
        if (canvas == null) canvas = coversRoot.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 200;
        canvas.pixelPerfect = false;

        if (coversRoot.GetComponent<CanvasScaler>() == null)
        {
            var scaler = coversRoot.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
        }
        if (coversRoot.GetComponent<GraphicRaycaster>() == null)
        {
            coversRoot.AddComponent<GraphicRaycaster>();
        }

        // Prefab root is Transform; keep SongDetail as the visible UI card and
        // enlarge the whole tree for overlay readability (~42% of 1080p height).
        var overlayScale = ComputeSongCoverOverlayScale();
        coversRoot.transform.localScale = Vector3.one * overlayScale;
        songDetail.localPosition = Vector3.zero;
        // Entry anim drives SongDetail scale; start from authored baseline.
        songDetail.localScale = Vector3.one;
        songDetail.gameObject.SetActive(true);

        // Ensure UIGraphics start opaque even if Entry has not advanced yet.
        foreach (var graphic in coversRoot.GetComponentsInChildren<Graphic>(true))
        {
            var color = graphic.color;
            color.a = 1f;
            graphic.color = color;
        }
    }

    static float ComputeSongCoverOverlayScale()
    {
        // CanvasScaler reference height is 1080; map prefab height to a fraction of it.
        var scale = 1080f * SongCoverTargetHeightFraction / SongDetailPrefabHeight;
        return Mathf.Clamp(scale, SongCoverMinScale, SongCoverMaxScale);
    }

    void EnsureSongDetailAnimator()
    {
        if (coversRoot == null) return;
        songDetailAnimator = coversRoot.GetComponent<Animator>();
        if (songDetailAnimator == null)
        {
            songDetailAnimator = coversRoot.AddComponent<Animator>();
        }
        if (songDetailAnimator.runtimeAnimatorController == null)
        {
            var controller = Resources.Load<RuntimeAnimatorController>(SongCoverAnimatorResource);
            if (controller != null)
            {
                songDetailAnimator.runtimeAnimatorController = controller;
            }
            else
            {
                Debug.LogWarning("[MJV][BGManager] Resources.Load failed for " + SongCoverAnimatorResource);
            }
        }
    }

    /// <summary>
    /// Desktop OpStart/Record equivalent: show jacket + chart metadata before notes.
    /// </summary>
    public void PlaySongDetail(string levelLabel = "")
    {
        BindSongDetail();
        if (coversRoot == null) return;

        if (titleText != null) titleText.text = string.IsNullOrEmpty(SimaiProcess.title) ? "" : SimaiProcess.title;
        if (artistText != null) artistText.text = string.IsNullOrEmpty(SimaiProcess.artist) ? "" : SimaiProcess.artist;
        if (desText != null) desText.text = string.IsNullOrEmpty(SimaiProcess.designer) ? "" : SimaiProcess.designer;
        if (idText != null) idText.text = levelLabel ?? "";

        if (jacketImage != null && spriteRender != null && spriteRender.sprite != null)
        {
            jacketImage.texture = spriteRender.sprite.texture;
        }

        coversRoot.SetActive(true);
        var songDetail = coversRoot.transform.Find("SongDetail");
        if (songDetail != null)
        {
            EnsureSongCoverOverlay(songDetail);
            songDetail.gameObject.SetActive(true);
        }

        EnsureSongDetailAnimator();
        if (songDetailAnimator != null && songDetailAnimator.runtimeAnimatorController != null)
        {
            songDetailAnimator.enabled = true;
            songDetailAnimator.Rebind();
            songDetailAnimator.Update(0f);
            songDetailAnimator.Play("Entry", 0, 0f);
            // Advance a few frames so Entry does not leave the card fully transparent.
            songDetailAnimator.Update(0.35f);
        }

        Debug.Log(
            "[MJV][BGManager] PlaySongDetail title=" +
            (titleText != null ? titleText.text : "") +
            " scale=" +
            ComputeSongCoverOverlayScale()
        );
    }

    private void VideoPlayer_errorReceived(VideoPlayer source, string message)
    {
        Debug.LogWarning("[MJV][BGManager] LoadVideoFailed: " + message);
        UseStaticBackground("VideoPlayer.errorReceived");
    }

    public void UseStaticBackground(string reason)
    {
        isAnyErr = true;
        showIdleVideoFrame = false;

        if (spriteRender != null)
        {
            spriteRender.forceRenderingOff = false;
        }

        Debug.LogWarning("[MJV][BGManager] use static background reason=" + reason);
    }

    public void SetNewSpriteForVideo()
    {
        videoTarget.GetComponent<SpriteRenderer>().sprite =
                Sprite.Create(new Texture2D(480, 480), new Rect(0, 0, 480, 480), new Vector2(0.5f, 0.5f));
    }

    public void SetIdleVideoFrameVisible(bool visible, string reason)
    {
        showIdleVideoFrame = visible && !isAnyErr;

        Debug.Log(
            "[MJV][BGManager] SetIdleVideoFrameVisible visible=" +
            showIdleVideoFrame +
            " requested=" +
            visible +
            " reason=" +
            reason +
            " isAnyErr=" +
            isAnyErr
        );
    }

    public void UpdateVideoRatio()
    {
        if (videoPlayer == null ||
            videoTarget == null ||
            videoPlayer.width <= 0 ||
            videoPlayer.height <= 0)
        {
            Debug.LogWarning("[MJV][BGManager] UpdateVideoRatio skipped: invalid video size");
            return;
        }
        Debug.LogWarning("[MJV][BGManager] UpdateVideoRatio");
        var scale = videoPlayer.height / (float)videoPlayer.width;
        videoTarget.transform.localScale = new Vector3(2.25f, 2.25f * scale);
    }

    public void SetPlayBackSpeed(float speed)
    {
        desireSpeed = speed;
        if (videoPlayer.canSetPlaybackSpeed)
        {
            videoPlayer.playbackSpeed = desireSpeed;
        }
        else
        {
            Debug.Log("[MJV][BGManager] videoPlayer.canSetPlaybackSpeed is false");
        }
    }

    public void Update()
    {
        var hideStaticBackground = false;

        if (!isAnyErr && videoPlayer != null)
        {
            hideStaticBackground = videoPlayer.isPlaying || showIdleVideoFrame;
        }

        if (spriteRender != null)
        {
            spriteRender.forceRenderingOff = hideStaticBackground;
        }

        if (hideStaticBackground != lastHideStaticBackground)
        {
            lastHideStaticBackground = hideStaticBackground;

            Debug.Log(
                "[MJV][BGManager] staticBackgroundHidden=" +
                hideStaticBackground +
                " videoPlaying=" +
                (videoPlayer != null && videoPlayer.isPlaying) +
                " videoPrepared=" +
                (videoPlayer != null && videoPlayer.isPrepared) +
                " idleFrame=" +
                showIdleVideoFrame
            );
        }

        if (BackgroundCover != null && settings != null)
        {
            BackgroundCover.color = new UnityEngine.Color(0f, 0f, 0f, settings.bgCover);
        }

        if (videoPlayer.isPrepared && videoPlayer.isPlaying)
        {
            var delta = videoPlayer.time - audioTimeProvider.AudioTime;
            if (Math.Abs(delta) > 0.1f)
            {
                Debug.Log("[MJV][BGManager] video time is behind audio time, try speed up video");
                if (videoPlayer.canSetPlaybackSpeed)
                {
                    float speedchange = 1f + ((float)-delta * 0.8f);
                    videoPlayer.playbackSpeed = desireSpeed * speedchange;
                }
                else
                {
                    Debug.Log("[MJV][BGManager] videoPlayer.canSetPlaybackSpeed is false");
                }
            }
            else
            {
                if (videoPlayer.canSetPlaybackSpeed)
                {
                    videoPlayer.playbackSpeed = desireSpeed;
                }
            }
        }
    }
}
