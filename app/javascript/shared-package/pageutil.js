var KAConsole = {
    debugEnabled: false,
    log: function() {
        if (window.console && KAConsole.debugEnabled) {
            if (console.log.apply)
                console.log.apply(console, arguments);
            else
                Function.prototype.apply.call(console.log, null, arguments);
        }
    }
};

function addCommas(nStr) // to show clean number format for "people learning right now" -- no built in JS function
{
    nStr += "";
    var x = nStr.split(".");
    var x1 = x[0];
    var x2 = x.length > 1 ? "." + x[1] : "";
    var rgx = /(\d+)(\d{3})/;
    while (rgx.test(x1)) {
        x1 = x1.replace(rgx, "$1" + "," + "$2");
    }
    return x1 + x2;
}

function validateEmail(sEmail)
{
     var re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
     return sEmail.match(re);
}

function addAutocompleteMatchToList(list, match, kind, reMatch) {
    var o = {
                "label": match.title,
                "title": match.title,
                "value": match.relative_url || match.ka_url,
                "key": match.key,
                "kind": kind
            };

    if (reMatch)
        o.label = o.label.replace(reMatch, "<b>$1</b>");

    list[list.length] = o;
}

function initAutocomplete(selector, fTopics, fxnSelect, fIgnoreSubmitOnEnter)
{
    var autocompleteWidget = $(selector).autocomplete({
        delay: 150,
        source: function(req, fxnCallback) {

            var term = $.trim(req.term);
            if (term.length < 2) {
                fxnCallback([]);
                return;
            }

            // Get autocomplete matches
            $.getJSON("/api/v1/autocomplete", {"q": term}, function(data) {

                var matches = [];

                if (data != null)
                {
                    var reMatch = null;

                    // Try to find the "scent" of the match.  If regexp fails
                    // to compile for any input reason, ignore.
                    try {
                        reMatch = new RegExp("(" + data.query + ")", "i");
                    }
                    catch (e) {
                        reMatch = null;
                    }

                    // Add topic and video matches to list of autocomplete suggestions

                    if (fTopics) {
                        for (var ix = 0; ix < data.topics.length; ix++) {
                            addAutocompleteMatchToList(matches, data.topics[ix], "topic", reMatch);
                        }
                    }
                    for (var ix = 0; ix < data.videos.length; ix++) {
                        addAutocompleteMatchToList(matches, data.videos[ix], "video", reMatch);
                    }
                    for (var ix = 0; ix < data.exercises.length; ix++) {
                        addAutocompleteMatchToList(matches, data.exercises[ix], "exercise", reMatch);
                    }
                }

                fxnCallback(matches);

            });
        },
        focus: function() {
            return false;
        },
        select: function(e, ui) {
            if (fxnSelect)
                fxnSelect(ui.item);
            else
                window.location = ui.item.value;
            return false;
        },
        open: function(e, ui) {
            var jelMenu = $(autocompleteWidget.data("autocomplete").menu.element);
            var jelInput = $(this);

            var pxRightMenu = jelMenu.offset().left + jelMenu.outerWidth();
            var pxRightInput = jelInput.offset().left + jelInput.outerWidth();
            var delta = pxRightMenu - pxRightInput

            if (delta != 0)
            {
                // Keep right side of search input and autocomplete menu aligned
                jelMenu.offset({left: jelMenu.offset().left - delta});
            }
        }
    }).bind("keydown.autocomplete", function(e) {
        if (!fIgnoreSubmitOnEnter && e.keyCode == $.ui.keyCode.ENTER || e.keyCode == $.ui.keyCode.NUMPAD_ENTER)
        {
            if (!autocompleteWidget.data("autocomplete").selectedItem)
            {
                // If enter is pressed and no item is selected, default autocomplete behavior
                // is to do nothing.  We don't want this behavior, we want to fall back to search.
                $(this.form).submit();
            }
        }
    });

    autocompleteWidget.data("autocomplete")._renderItem = function(ul, item) {
        // Customize the display of autocomplete suggestions
        var jLink = $("<a></a>").html(item.label);
        if (item.kind == "topic")
            jLink.prepend("<span class='autocomplete-topic'>נושא </span>");
        else if (item.kind == "video")
            jLink.prepend("<span class='autocomplete-video'>סרטון </span>");
        else if (item.kind == "exercise")
            jLink.prepend("<span class='autocomplete-exercise'>תרגיל </span>");

        return $("<li></li>")
            .data("item.autocomplete", item)
            .append(jLink)
            .appendTo(ul);
    };

    autocompleteWidget.data("autocomplete").menu.select = function(e) {
        // jquery-ui.js's ui.autocomplete widget relies on an implementation of ui.menu
        // that is overridden by our jquery.ui.menu.js.  We need to trigger "selected"
        // here for this specific autocomplete box, not "select."
        this._trigger("selected", e, { item: this.active });
    };
}

$(function() {
    // Configure the search form
    if ($("#page_search input[type=text]").placeholder().length) {
        initAutocomplete("#page_search input[type=text]", true);
    }

    $("#page_search").submit(function(e) {
        // Only allow submission if there is a non-empty query.
        return !!$.trim($("#page_search input[type=text]").val());
    });
});

var Badges = {

    show: function(sBadgeContainerHtml) {
        var jel = $(".badge-award-container");

        if (sBadgeContainerHtml)
        {
            jel.remove();
            $("body").append(sBadgeContainerHtml);
            jel = $(".badge-award-container");

            if (jel.length) Social.init(jel);
        }

        if (!jel.length) return;

        $(".achievement-badge", jel).click(function() {
            window.location = KA.profileRoot + "/achievements";
            return false;
        });

        var jelTarget = $(".badge-target");
        var jelContainer = $("#page-container-inner");

        var top = jelTarget.offset().top + jelTarget.height() + 5;

        setTimeout(function() {
            jel.css("visibility", "hidden").css("display", "");
            jel.css("right", jelContainer.offset().left + (jelContainer.width() / 2) - (jel.width() / 2)).css("top", -1 * jel.height());
            var topBounce = top + 10;
            jel.css("display", "").css("visibility", "visible");
            jel.animate({top: topBounce}, 300, function() {jel.animate({top: top}, 100);});
        }, 100);
    },

    hide: function() {
        var jel = $(".badge-award-container");
        jel.animate({top: -1 * jel.height()}, 500, function() {jel.hide();});
    },

    showMoreContext: function(el) {
        var jelLink = $(el).parents(".badge-context-hidden-link");
        var jelBadge = jelLink.parents(".achievement-badge");
        var jelContext = $(".badge-context-hidden", jelBadge);

        if (jelLink.length && jelBadge.length && jelContext.length)
        {
            $(".ellipsis", jelLink).remove();
            jelLink.html(jelLink.text());
            jelContext.css("display", "");
            jelBadge.find(".achievement-desc").addClass("expanded");
            jelBadge.css("min-height", jelBadge.css("height")).css("height", "auto");
            jelBadge.nextAll(".achievement-badge").first().css("clear", "both");
        }
    }
};

var Notifications = {

    show: function(sNotificationContainerHtml) {
        var jel = $(".notification-bar");

        if (sNotificationContainerHtml)
        {
            var jelNew = $(sNotificationContainerHtml);
            jel.empty().append(jelNew.children());
        }

        $(".notification-bar-close a").click(function() {
            Notifications.hide();
            return false;
        });

        if (!jel.is(":visible")) {
            setTimeout(function() {

                jel
                    .css("visibility", "hidden")
                    .css("display", "")
                    .css("top", -jel.height() - 2) // 2 for border and outline
                    .css("visibility", "visible");

                // Queue:false to make sure all of these run at the same time
                var animationOptions = {duration: 350, queue: false};

                $(".notification-bar-spacer").animate({ height: 35 }, animationOptions);
                jel.show().animate({ top: 0 }, animationOptions);

            }, 100);
        }
    },
    showTemplate: function(templateName) {
        var template = Templates.get(templateName);
        this.show(template());
    },

    hide: function() {
        var jel = $(".notification-bar");

        // Queue:false to make sure all of these run at the same time
        var animationOptions = {duration: 350, queue: false};

        $(".notification-bar-spacer").animate({ height: 0 }, animationOptions);
        jel.animate(
                { top: -jel.height() - 2 }, // 2 for border and outline
                $.extend({}, animationOptions,
                    { complete: function() { jel.empty().css("display", "none"); } }
                )
        );

        $.post("/notifierclose");
    }
};

var Timezone = {
    tz_offset: null,

    append_tz_offset_query_param: function(href) {
        if (href.indexOf("?") > -1)
            href += "&";
        else
            href += "?";
        return href + "tz_offset=" + Timezone.get_tz_offset();
    },

    get_tz_offset: function() {
        if (this.tz_offset == null)
            this.tz_offset = -1 * (new Date()).getTimezoneOffset();
        return this.tz_offset;
    }
};

// not every browser has Date.prototype.toISOString
// https://developer.mozilla.org/en/JavaScript/Reference/Global_Objects/Date#Example.3a_ISO_8601_formatted_dates
if (!Date.prototype.toISOString) {
    Date.prototype.toISOString = function() {
        var pad = function(n) { return n < 10 ? "0" + n : n; };
            return this.getUTCFullYear() + "-" +
                pad(this.getUTCMonth() + 1) + "-" +
                pad(this.getUTCDate()) + "T" +
                pad(this.getUTCHours()) + ":" +
                pad(this.getUTCMinutes()) + ":" +
                pad(this.getUTCSeconds()) + "Z";
    };
}

// some browsers can't parse ISO 8601 with Date.parse
// http://anentropic.wordpress.com/2009/06/25/javascript-iso8601-parser-and-pretty-dates/
var parseISO8601 = function(str) {
    // we assume str is a UTC date ending in 'Z'
    var parts = str.split("T"),
        dateParts = parts[0].split("-"),
        timeParts = parts[1].split("Z"),
        timeSubParts = timeParts[0].split(":"),
        timeSecParts = timeSubParts[2].split("."),
        timeHours = Number(timeSubParts[0]),
        _date = new Date();

    _date.setUTCFullYear(Number(dateParts[0]));
    _date.setUTCMonth(Number(dateParts[1]) - 1);
    _date.setUTCDate(Number(dateParts[2]));
    _date.setUTCHours(Number(timeHours));
    _date.setUTCMinutes(Number(timeSubParts[1]));
    _date.setUTCSeconds(Number(timeSecParts[0]));
    if (timeSecParts[1]) {
        _date.setUTCMilliseconds(Number(timeSecParts[1]));
    }

    // by using setUTC methods the date has already been converted to local time(?)
    return _date;
};

var MailingList = {
    init: function(sIdList) {
        var jelMailingListContainer = $("#mailing_list_container_" + sIdList);
        var jelMailingList = $("form", jelMailingListContainer);
        var jelEmail = $(".email", jelMailingList);

        jelEmail.placeholder().change(function() {
            $(".error", jelMailingListContainer).css("display", (!$(this).val() || validateEmail($(this).val())) ? "none" : "");
        }).keypress(function() {
            if ($(".error", jelMailingListContainer).is(":visible") && validateEmail($(this).val()))
                $(".error", jelMailingListContainer).css("display", "none");
        });

        jelMailingList.submit(function(e) {
            if (validateEmail(jelEmail.val()))
            {
                $.post("/mailing-lists/subscribe", {list_id: sIdList, email: jelEmail.val()});
                jelMailingListContainer.html("<p>Done!</p>");
            }
            e.preventDefault();
            return false;
        });
    }
};

var CSSMenus = {

    active_menu: null,

    init: function() {
        // Make the CSS-only menus click-activated
        $(".noscript").removeClass("noscript");
        $(document).delegate(".css-menu > ul > li", "click", function() {
            if (CSSMenus.active_menu)
                CSSMenus.active_menu.removeClass("css-menu-js-hover");

            if (CSSMenus.active_menu && this == CSSMenus.active_menu[0])
                CSSMenus.active_menu = null;
            else
                CSSMenus.active_menu = $(this).addClass("css-menu-js-hover");
        });

        $(document).bind("click focusin", function(e) {
            if (CSSMenus.active_menu &&
                $(e.target).closest(".css-menu").length === 0) {
                CSSMenus.active_menu.removeClass("css-menu-js-hover");
                CSSMenus.active_menu = null;
            }
        });

        // Make the CSS-only menus keyboard-accessible
        $(document).delegate(".css-menu a", {
            focus: function(e) {
                $(e.target)
                    .addClass("css-menu-js-hover")
                    .closest(".css-menu > ul > li")
                        .addClass("css-menu-js-hover");
            },
            blur: function(e) {
                $(e.target)
                    .removeClass("css-menu-js-hover")
                    .closest(".css-menu > ul > li")
                        .removeClass("css-menu-js-hover");
            }
        });
    }
};
$(CSSMenus.init);

var IEHtml5 = {
    init: function() {
        // Create a dummy version of each HTML5 element we use so that IE 6-8 can style them.
        var html5elements = ["header", "footer", "nav", "article", "section", "menu"];
        for (var i = 0; i < html5elements.length; i++) {
            document.createElement(html5elements[i]);
        }
   }
};
IEHtml5.init();

var VideoViews = {
    init: function() {
        // Fit calculated early Feb 2012
        var estimatedTotalViews = -4.792993409561827e9 + 3.6966675231488018e-3 * (+new Date());

        var totalViewsString = addCommas("" + Math.round(estimatedTotalViews));

        $("#page_num_visitors").append(totalViewsString);
        $("#page_visitors").css("display", "inline");
    }
};
$(VideoViews.init);

var FacebookHook = {
    init: function() {
        if (!window.FB_APP_ID) return;

        window.fbAsyncInit = function() {
            FB.init({appId: FB_APP_ID, status: true, cookie: true, xfbml: true, oauth: true});

            if (!USERNAME) {
                FB.Event.subscribe("auth.login", FacebookHook.postLogin);
            }

            FB.getLoginStatus(function(response) {

                if (response.authResponse) {
                    FacebookHook.fixMissingCookie(response.authResponse);
                }

                $("#page_logout").click(function(e) {

                    eraseCookie("fbsr_" + FB_APP_ID);

                    if (response.authResponse) {

                        FB.logout(function() {
                            window.location = $("#page_logout").attr("href");
                        });

                        e.preventDefault();
                        return false;
                    }

                });

            });
        };

        $(function() {
            var e = document.createElement("script"); e.async = true;
            e.src = document.location.protocol + "//connect.facebook.net/en_US/all.js";
            document.getElementById("fb-root").appendChild(e);
        });
    },

    doLogin: function() {
        FB.login(FacebookHook.postLogin, {})
    },

    postLogin: function(response) {

        if (response.authResponse) {
            FacebookHook.fixMissingCookie(response.authResponse);
        }

        var url = URL_CONTINUE || "/";
        if (url.indexOf("?") > -1)
            url += "&fb=1";
        else
            url += "?fb=1";

        var hasCookie = !!readCookie("fbsr_" + FB_APP_ID);
        url += "&hc=" + (hasCookie ? "1" : "0");

        url += "&hs=" + (response.authResponse ? "1" : "0");

                window.location = url;
    },

    fixMissingCookie: function(authResponse) {
        // In certain circumstances, Facebook's JS SDK fails to set their cookie
        // but still thinks users are logged in. To avoid continuous reloads, we
        // set the cookie manually. See http://forum.developers.facebook.net/viewtopic.php?id=67438.

        if (readCookie("fbsr_" + FB_APP_ID))
            return;

        if (authResponse && authResponse.signedRequest) {
            // Explicitly use a session cookie here for IE's sake.
            createCookie("fbsr_" + FB_APP_ID, authResponse.signedRequest);
        }
    }

};
FacebookHook.init();

var Throbber = {
    jElement: null,

    show: function(jTarget, fOnLeft) {
        if (!Throbber.jElement)
        {
            Throbber.jElement = $("<img style='display:none;' src='/images/throbber.gif' class='throbber'/>");
            $(document.body).append(Throbber.jElement);
        }

        if (!jTarget.length) return;

        var offset = jTarget.offset();

        var top = offset.top + (jTarget.outerHeight() / 2) - 8;
        var left = fOnLeft ? (offset.left + jTarget.outerWidth() - 16 - 4) : (offset.left + 4);

        Throbber.jElement.css("top", top).css("left", left).css("display", "");
        Throbber.jElement.zIndex(jTarget.zIndex()+10);
    },

    hide: function() {
        if (Throbber.jElement) Throbber.jElement.css("display", "none");
    }
};

var SearchResultHighlight = {
    doReplace: function(word, element) {
        // Find all text elements
        textElements = $(element).contents().filter(function() { return this.nodeType != 1; });
        textElements.each(function(index, textElement) {
            var pos = textElement.data.toLowerCase().indexOf(word);
            if (pos >= 0) {
                // Split text element into three elements
                var highlightText = textElement.splitText(pos);
                highlightText.splitText(word.length);

                // Highlight the matching text
                $(highlightText).wrap('<span class="highlighted" />');
            }
        });
    },
    highlight: function(query) {
        $(".searchresulthighlight").each(function(index, element) {
            SearchResultHighlight.doReplace(query, element);
        });
    }
};

// This function detaches the passed in jQuery element and returns a function that re-attaches it
function temporaryDetachElement(element, fn, context) {
    var el, reattach;
    el = element.next();
    if (el.length > 0) {
        // This element belongs before some other element
        reattach = function() {
            element.insertBefore(el);
        };
    } else {
        // This element belongs at the end of the parent's child list
        el = element.parent();
        reattach = function() {
            element.appendTo(el);
        };
    }
    element.detach();
    var val = fn.call(context || this, element);
    reattach();
    return val;
}

var globalPopupDialog = {
    visible: false,
    bindings: false,

    // Size can be an array [width,height] to have an auto-centered dialog or null if the positioning is handled in CSS
    show: function(className, size, title, html, autoClose) {
        var css = (!size) ? {} : {
            position: "relative",
            width: size[0],
            height: size[1],
            marginLeft: (-0.5*size[0]).toFixed(0),
            marginTop: (-0.5*size[1] - 100).toFixed(0)
        }
        $("#popup-dialog")
            .hide()
            .find(".dialog-frame")
                .attr("class", "dialog-frame " + className)
                .attr('style', '') // clear style
                .css(css)
                .find(".description")
                    .html('<h3>' + title + '</h3>')
                    .end()
                .end()
            .find(".dialog-contents")
                .html(html)
                .end()
            .find(".close-button")
                .click(function() { globalPopupDialog.hide(); })
                .end()
            .show()

        if (autoClose && !globalPopupDialog.bindings) {
            // listen for escape key
            $(document).bind('keyup.popupdialog', function ( e ) {
                if ( e.which == 27 ) {
                    globalPopupDialog.hide();
                }
            });

            // close the goal dialog if user clicks elsewhere on page
            $('body').bind('click.popupdialog', function( e ) {
                if ( $(e.target).closest('.dialog-frame').length === 0 ) {
                    globalPopupDialog.hide();
                }
            });
            globalPopupDialog.bindings = true;
        } else if (!autoClose && globalPopupDialog.bindings) {
            $(document).unbind('keyup.popupdialog');
            $('body').unbind('click.popupdialog');
            globalPopupDialog.bindings = false;
        }

        globalPopupDialog.visible = true;
        return globalPopupDialog;
    },
    hide: function() {
        if (globalPopupDialog.visible) {
            $("#popup-dialog")
                .hide()
                .find(".dialog-contents")
                    .html('');

            if (globalPopupDialog.bindings) {
                $(document).unbind('keyup.popupdialog');
                $('body').unbind('click.popupdialog');
                globalPopupDialog.bindings = false;
            }

            globalPopupDialog.visible = false;
        }
        return globalPopupDialog;
    }
};

(function() {
    var messageBox = null;

    popupGenericMessageBox = function(options) {
        if (messageBox) {
            $(messageBox).modal('hide').remove();
        }

        options = _.extend({
            buttons: [
                { title: 'OK', action: hideGenericMessageBox }
            ]
        }, options);

        var template = Templates.get( "shared.generic-dialog" );
        messageBox = $(template(options)).appendTo(document.body).modal({
            keyboard: true,
            backdrop: true,
            show: true
        }).get(0);

        _.each(options.buttons, function(button) {
            $('.generic-button[data-id="' + button.title + '"]', $(messageBox)).click(button.action);
        });
    }

    hideGenericMessageBox = function() {
        if (messageBox) {
            $(messageBox).modal('hide');
        }
        messageBox = null;
    }
})();

function dynamicPackage(packageName, callback, manifest) {
    var self = this;
    this.files = [];
    this.progress = 0;
    this.last_progress = 0;

    dynamicPackageLoader.loadingPackages[packageName] = this;
    _.each(manifest, function(filename) {
        var file = {
            "filename": filename,
            "content": null,
            "evaled": false
        };
        self.files.push(file);
        $.ajax({
            type: "GET",
            url: filename,
            data: null,
            success: function(content) {
                            KAConsole.log("Received contents of " + filename);
                            file.content = content;

                            self.progress++;
                            callback("progress", self.progress / (2 * self.files.length));
                            self.last_progress = self.progress;
                        },
            error: function(xml, status, e) {
                            callback("failed");
                        },
            dataType: "html"
        });
    });

    this.checkComplete = function() {
        var waiting = false;
        _.each(this.files, function(file) {
            if (file.content) {
                if (!file.evaled) {
                    var script = document.createElement("script");
                    if (file.filename.indexOf(".handlebars") > 0)
                        script.type = "text/x-handlebars-template"; // This hasn't been tested
                    else
                        script.type = "text/javascript";

                    script.text = file.content;

                    var head = document.getElementsByTagName("head")[0] || document.documentElement;
                    head.appendChild(script);

                    file.evaled = true;
                    KAConsole.log("Evaled contents of " + file.filename);

                    self.progress++;
                }
            } else {
                waiting = true;
                return _.breaker;
            }
        });

        if (waiting) {
            if (self.progress != self.last_progress) {
                callback("progress", self.progress / (2 * self.files.length));
                self.last_progress = self.progress;
            }
            setTimeout(function() { self.checkComplete(); }, 500);
        } else {
            dynamicPackageLoader.loadedPackages[packageName] = true;
            delete dynamicPackageLoader.loadingPackages[packageName];
            callback("complete");
        }
    };

    this.checkComplete();
}

var dynamicPackageLoader = {
    loadedPackages: {},
    loadingPackages: {},
    currentFiles: [],

    load: function(packageName, callback, manifest) {
        if (this.loadedPackages[packageName]) {
            if (callback)
                callback(packageName);
        } else {
            new dynamicPackage(packageName, callback, manifest);
        }
    },

    packageLoaded: function(packageName) {
        return this.loadedPackages[packageName];
    },

    setPackageLoaded: function(packageName) {
        this.loadedPackages[packageName] = true;
    }
};

$(function() {
    $(document).delegate("input.blur-on-esc", "keyup", function(e, options) {
        if (options && options.silent) return;
        if (e.which == "27") {
            $(e.target).blur();
        }
    });
});

// An animation that grows a box shadow of the review hue
$.fx.step.reviewExplode = function(fx) {
    var val = fx.now + fx.unit;
    $(fx.elem).css("boxShadow",
        "0 0 " + val + " " + val + " " + "rgba(227, 93, 4, 0.2)");
};

var Review = {
    REVIEW_DONE_HTML: "Review&nbsp;Done!",

    highlightDone: function() {
        if ($("#review-mode-title").hasClass("review-done")) {
            return;
        }

        var duration = 800;

        // Make the explosion flare overlap all other elements
        var overflowBefore = $("#container").css("overflow");
        $("#container").css("overflow", "visible")
            .delay(duration).queue(function() {
                $(this).css("overflow", overflowBefore);
            });

        // Review hue explosion
        $("#review-mode-title").stop().addClass("review-done").animate({
            reviewExplode: 200
        }, duration).queue(function() {
            $(this).removeAttr("style").addClass("post-animation");
        });

        // Temporarily change the color of the review done box to match the explosion
        $("#review-mode-title > div")
            .css("backgroundColor", "#F9DFCD")
            .delay(duration).queue(function() {
                $(this).removeAttr("style").addClass("review-done");
            });

        // Huge "REVIEW DONE!" text shrinks to fit in its box
        $("#review-mode-title h1").html(Review.REVIEW_DONE_HTML).css({
            fontSize: "100px",
            right: 0,
            position: "absolute"
        }).stop().animate({
            reviewGlow: 1,
            opacity: 1,
            fontSize: 30
        }, duration).queue(function() {
            $(this).removeAttr("style");
        });
    },

    initCounter: function(reviewsLeftCount) {
        var digits = "0 1 2 3 4 5 6 7 8 9 ";
        $("#review-counter-container")
            .find(".ones").text(new Array(10 + 1).join(digits)).end()
            .find(".tens").text(digits);
    },

    updateCounter: function(reviewsLeftCount) {

        // Spin the remaining reviews counter like a slot machine
        var reviewCounterElem = $("#review-counter-container"),
            reviewTitleElem = $("#review-mode-title"),
            oldCount = reviewCounterElem.data("counter") || 0,
            tens = Math.floor((reviewsLeftCount % 100) / 10),
            animationOptions = {
                duration: Math.log(1 + Math.abs(reviewsLeftCount - oldCount)) *
                    1000 * 0.5 + 0.2,
                easing: "easeInOutCubic"
            },
            lineHeight = parseInt(
                reviewCounterElem.children().css("lineHeight"), 10);

        reviewCounterElem.find(".ones").animate({
            top: (reviewsLeftCount % 100) * -lineHeight
        }, animationOptions);

        reviewCounterElem.find(".tens").animate({
            top: tens * -lineHeight
        }, animationOptions);

        if (reviewsLeftCount === 0) {
            if (oldCount > 0) {
                // Review just finished, light a champagne supernova in the sky
                Review.highlightDone();
            } else {
                reviewTitleElem
                    .addClass("review-done post-animation")
                    .find("h1")
                    .html(Review.REVIEW_DONE_HTML);
            }
        } else if (!reviewTitleElem.hasClass("review-done")) {
            $("#review-mode-title h1").text(
                reviewsLeftCount === 1 ? "Exercise Left!" : "Exercises Left");
        }

        reviewCounterElem.data("counter", reviewsLeftCount);
    }
};
function showAssociations() {
    $("#associations").toggle({effect: "drop", direction: "right"});
    setTimeout(function() {
        $(".logo-ani10").toggle({effect: "drop", direction: "right"})
    }, 200);
}

$(function() {
    if (document.referrer.indexOf(location.protocol + "//" + location.host) === 0) {
        $("#associations").show();
        $(".logo-ani10").show();
    } else {
        setTimeout(showAssociations, 2000);
    }
})

var TopicNav = {

    updateHash: function(hash) {
        if (!TopicNav.hashSupport) {
            // disabled;
            return;
        }
        if (window.location.hash.slice(1) == hash) {
            // no need;
            return;
        }
        TopicNav.allowOnHashChange = false;
        window.location.hash = hash;
    },

    openTopic: function(topic_id, speed, no_jump) {
        var topic_anchor = $("#" + topic_id + ".heading:first");
        if (topic_anchor.length != 1) {
            // not found
            return;
        } else if (topic_anchor.hasClass("active")) {
            console.log("topic '" + topic_id + "' already selected");
            return;
        }

        if (typeof speed == "undefined")
            speed = 500;

        // first close all sybling content (including current)
        // content < li < ul > contents
        $("#library-content-main a.heading.active").removeClass("active", speed);
        topic_anchor.addClass("active", speed);

        var to_show = topic_anchor
            .next(".content")
            .parents(".content")
            .andSelf();

        var to_hide = $("#library-content-main .content:visible")
            .not(to_show);

        to_hide.filter(":visible").slideUp(speed);
        to_show.filter(":hidden").slideDown(speed);

        setTimeout(function() { TopicNav.colorizeHeaders(speed); }, speed+5);

        $("#library-content-main span.ui-icon").removeClass("ui-icon-triangle-1-s").addClass("ui-icon-triangle-1-w");
        to_show.prev().children("span.ui-icon").addClass("ui-icon-triangle-1-s").removeClass("ui-icon-triangle-1-w");

        if (no_jump) {
            return;
        }

        var scroll_target = topic_anchor.parent().offset().top;
        if (to_hide.length > 0 && to_hide.offset().top < scroll_target) {
            scroll_target -= to_hide.height();
        }
        scroll_target -= topic_anchor.outerHeight();  // give some context

        $('html, body').animate({scrollTop: scroll_target}, speed);

        TopicNav.updateHash(topic_id.slice(1));
    },

    hashSupport: true,
    allowOnHashChange: true,

    colorizeHeaders: function(speed) {
        $("#library-content-main .heading:visible:even").addClass("even", speed);
        $("#library-content-main .heading:visible:odd").removeClass("even", speed);
    },

    init: function(hashSupport) {

        TopicNav.hashSupport = typeof hashSupport === "undefined" ? true : hashSupport;

        TopicNav.colorizeHeaders();

        $("#library-content-main a.heading").click(function(event) {
            var content = $(this).next(".content");
            if (content.is(":visible")) {
                // this item is already open - close by selecting the parent
                var parent_topic = content.parents(".content:first").prev("a.heading");
                if (parent_topic.length > 0)
                    TopicNav.openTopic(parent_topic[0].id);
                else
                    TopicNav.openTopic(this.id);
            } else {
                TopicNav.openTopic(this.id);
            }
            event.preventDefault();
        })

        if (!TopicNav.hashSupport) {
            // disabled
            return;
        }

        // register to has changes
        $(window).on('hashchange', function(event) {
            if (!TopicNav.allowOnHashChange) {
                TopicNav.allowOnHashChange = true;
                event.preventDefault();
            } else {
                var topic_anchor = $("#_" + window.location.hash.slice(1) + ".heading");
                if (topic_anchor.length > 0) {
                    event.preventDefault();
                    TopicNav.openTopic(topic_anchor[0].id, 0);
                }
            }
        });

        // jump to initial topic, if exists
        if (!window.location.hash.length ) {
            var first_topic = $("#library-content-main a.heading:first")[0];
            TopicNav.openTopic(first_topic.id, 0, true);
        } else {
            var topic_anchor = $("#_" + window.location.hash.slice(1) + ".heading");
            if (topic_anchor.length > 0) {
                $(function() { TopicNav.openTopic(topic_anchor[0].id, 0) });
            }
        }
    }
};
