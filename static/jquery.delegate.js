(function($) {

    $.fn.delegate = function(eventType, rules) {
        // In IE reset/submit do not bubble.
        // Safari 2 submit does not bubble.
        if (($.browser.msie && /reset|submit/.test(eventType))
            || ($.browser.safari && parseInt($.browser.version) < 500 && eventType == 'submit')) {

            if (eventType == 'reset') {
                // reset:
                // click [type=reset]
                // press escape [type=text], [type=password], textarea
                this.bind('click', function(e) {
                    var $target = $(e.target);
                    for (var selector in rules) {
                        if ($target.is('[type=reset]')
                            && $(e.target.form).is(selector)) {

                            arguments[0] = $.event.fix(e);
                            arguments[0].target = e.target.form;
                            arguments[0].type = eventType;
                            var ret = rules[selector].apply(this, arguments); // required to store in extra variable if confirm() is involved
                            return ret;
                        }
                    }
                });
                this.bind('keypress', function(e) {
                    var $target = $(e.target);
                    for (var selector in rules) {
                        if ($target.is('[type=text], [type=password], textarea')
                            && $(e.target.form).is(selector)
                            && e.keyCode == 27) {

                            arguments[0] = $.event.fix(e);
                            arguments[0].target = e.target.form;
                            arguments[0].type = eventType;
                            var ret = rules[selector].apply(this, arguments); // required to store in extra variable if confirm() is involved
                            return ret;
                        }
                    }
                });
            }

            if (eventType == 'submit') {
                // submit:
                // click [type=submit], [type=image]
                // press enter [type=text], [type=password], textarea
                this.bind('click', function(e) {
                    var $target = $(e.target);
                    for (var selector in rules) {

                        // Safari 2 quickfix for nested button elements
                        var form, button = e.target;
                        while (!(form = button.form))
                            button = button.parentNode;

                        if ($(button).is('[type=submit], [type=image]')
                            && $(form).is(selector)) {

                            arguments[0] = $.event.fix(e);
                            arguments[0].target = form;
                            arguments[0].type = eventType;
                            var ret = rules[selector].apply(this, arguments); // required if confirm() is involved
                            return ret;
                        }
                    }
                });
                this.bind('keypress', function(e) {
                    var $target = $(e.target);
                    for (var selector in rules) {
                        if ($target.is('[type=text], [type=password], textarea')
                            && $(e.target.form).is(selector)
                            && e.keyCode == 13) {

                            arguments[0] = $.event.fix(e);
                            arguments[0].target = e.target.form;
                            arguments[0].type = eventType;
                            var ret = rules[selector].apply(this, arguments); // required if confirm() is involved
                            return ret;
                        }
                    }
                });
            }

            return this;
        }

        return this.bind(eventType, function(e) {
            var $target = $(e.target);
            for (var selector in rules)
                if ($target.is(selector))
                    return rules[selector].apply(this, arguments);
        });
    };

})(jQuery);