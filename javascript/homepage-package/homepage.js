var Homepage = {

    init: function() {
        VideoControls.initThumbnails();
        Homepage.initWaypoints();
        Homepage.loadData();
    },

    initPlaceholder: function(youtube_id) {

        var jelPlaceholder = $("#main-video-placeholder");

        // Once the youtube player is all loaded and ready, clicking the play
        // button will play inline.
        $(VideoControls).one("playerready", function() {

            // Before any playing, unveil and play the real youtube player
            $(VideoControls).one("beforeplay", function() {

                // Use .left to unhide the player without causing any
                // re-rendering or "pop"-in of the player.
                $(".player-loading-wrapper").css("left", 0);

                jelPlaceholder.find(".youtube-play").css("visibility", "hidden");

            });

            jelPlaceholder.click(function(e) {

                VideoControls.play();
                e.preventDefault();

            });

        });

        // Start loading the youtube player immediately,
        // and insert it wrapped in a hidden container
        var template = Templates.get("shared.youtube-player");

        jelPlaceholder
            .parents("#main-video-link")
                .after(
                    $(template({"youtubeId": youtube_id}))
                        .wrap("<div class='player-loading-wrapper'/>")
                        .parent()
            );
    },

    initWaypoints: function() {

        // Waypoint behavior not supported in IE7-
        if ($.browser.msie && parseInt($.browser.version, 10) < 8) return;

        $.waypoints.settings.scrollThrottle = 50;

        $("#browse").waypoint(function(event, direction) {

            var jel = $(this);
            var jelFixed = $("#browse-fixed");
            var jelTop = $("#back-to-top");

            jelTop.click(function() {Homepage.waypointTop(jel, jelFixed, jelTop);});

            if (direction == "down")
                Homepage.waypointVideos(jel, jelFixed, jelTop);
            else
                Homepage.waypointTop(jel, jelFixed, jelTop);
        });
    },

    waypointTop: function(jel, jelFixed, jelTop) {
        jelFixed.css("display", "none");
        if (!$.browser.msie) jelTop.css("display", "none");
    },

    waypointVideos: function(jel, jelFixed, jelTop) {
        jelFixed.css("width", jel.width()).css("display", "block");
        if (!$.browser.msie) jelTop.css("display", "block");
        if (CSSMenus.active_menu) CSSMenus.active_menu.removeClass("css-menu-js-hover");
    },

    /**
     * Loads the contents of the topic data.
     */
    loadData: function() {
        var cacheToken = window.Homepage_cacheToken;
        // Currently, this is being A/B tested with the conventional rendering
        // method (where everything is rendered on the server). If there is
        // no cache token, then we know we're using the old method, so don't
        // fetch the data.
        if (!cacheToken) {
            return;
        }
        $.ajax({
            type: "GET",
            url: "/api/v1/topics/library/compact",
            dataType: "jsonp",

            // The cacheToken is supplied by the host page to indicate when the library
            // was updated. Since it's fully cacheable, the browser can pull from the
            // local client cache if it has the data already.
            data: {"v": cacheToken},

            // Explicitly specify the callback, since jQuery will otherwise put in
            // a randomly named callback and break caching.
            jsonpCallback: "__dataCb",
            success: function(data) {
                Homepage.renderLibraryContent(data);
            },
            error: function() {
                KAConsole.log("Error loading initial library data.");
            },
            cache: true
        });
    },

    renderLibraryContent: function(topics) {
        var template = Templates.get("homepage.videolist");
        $.each(topics, function(i, topic) {
            var items = topic["children"];
            var itemsPerCol = Math.ceil(items.length / 3);
            var colHeight = itemsPerCol * 18;
            topic["colHeight"] = colHeight;
            topic["titleEncoded"] = encodeURIComponent(topic["title"]);
            for (var j = 0, item; item = items[j]; j++) {
                var col = (j / itemsPerCol) | 0;
                item["col"] = col;
                if ((j % itemsPerCol === 0) && col > 0) {
                    item["firstInCol"] = true;
                }
            }

            var container = $("#" + topic["id"] + " ol").get(0);
            container.innerHTML = template(topic);
        });

        topics = null;
    }
}

$(function() {Homepage.init();});

