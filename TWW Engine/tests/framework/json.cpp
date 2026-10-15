#include "framework/json.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace tww_engine {
namespace testing {
namespace {

const Json kNull;

struct Parser {
    const std::string& s;
    size_t i = 0;
    std::string err;

    explicit Parser(const std::string& text) : s(text) {}

    void skip_ws() {
        while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) {
            i++;
        }
    }

    bool fail(const char* what) {
        // Line and column, not a byte offset: some goldens are one 600K line.
        size_t line = 1, col = 1;
        for (size_t k = 0; k < i && k < s.size(); k++) {
            if (s[k] == '\n') {
                line++;
                col = 1;
            } else {
                col++;
            }
        }
        char buf[256];
        std::snprintf(buf, sizeof buf, "%s at line %zu column %zu", what, line, col);
        err = buf;
        return false;
    }

    bool lit(const char* word) {
        size_t n = std::strlen(word);
        if (s.compare(i, n, word) != 0) {
            return false;
        }
        i += n;
        return true;
    }

    bool parse_string(std::string* out) {
        if (i >= s.size() || s[i] != '"') {
            return fail("expected a string");
        }
        i++;
        out->clear();
        while (i < s.size() && s[i] != '"') {
            char ch = s[i];
            if (ch != '\\') {
                out->push_back(ch);
                i++;
                continue;
            }
            i++;
            if (i >= s.size()) {
                return fail("string ends inside an escape");
            }
            char e = s[i++];
            switch (e) {
                case '"': out->push_back('"'); break;
                case '\\': out->push_back('\\'); break;
                case '/': out->push_back('/'); break;
                case 'b': out->push_back('\b'); break;
                case 'f': out->push_back('\f'); break;
                case 'n': out->push_back('\n'); break;
                case 'r': out->push_back('\r'); break;
                case 't': out->push_back('\t'); break;
                case 'u': {
                    // \uXXXX: a BMP codepoint to UTF-8. Surrogates are refused, not paired
                    // (every golden string is ASCII).
                    if (i + 4 > s.size()) {
                        return fail("truncated \\u escape");
                    }
                    unsigned cp = 0;
                    for (int k = 0; k < 4; k++) {
                        char h = s[i + k];
                        cp <<= 4;
                        if (h >= '0' && h <= '9') {
                            cp |= unsigned(h - '0');
                        } else if (h >= 'a' && h <= 'f') {
                            cp |= unsigned(h - 'a' + 10);
                        } else if (h >= 'A' && h <= 'F') {
                            cp |= unsigned(h - 'A' + 10);
                        } else {
                            return fail("bad hex in \\u escape");
                        }
                    }
                    i += 4;
                    if (cp >= 0xD800 && cp <= 0xDFFF) {
                        return fail("surrogate pair in a golden string: this reader has never "
                                    "seen one and will not guess");
                    }
                    if (cp < 0x80) {
                        out->push_back(char(cp));
                    } else if (cp < 0x800) {
                        out->push_back(char(0xC0 | (cp >> 6)));
                        out->push_back(char(0x80 | (cp & 0x3F)));
                    } else {
                        out->push_back(char(0xE0 | (cp >> 12)));
                        out->push_back(char(0x80 | ((cp >> 6) & 0x3F)));
                        out->push_back(char(0x80 | (cp & 0x3F)));
                    }
                    break;
                }
                default:
                    return fail("unknown string escape");
            }
        }
        if (i >= s.size()) {
            return fail("string is never closed");
        }
        i++;  // the closing quote
        return true;
    }

    bool parse_value(Json* out) {
        skip_ws();
        if (i >= s.size()) {
            return fail("value expected, input ended");
        }
        char ch = s[i];
        if (ch == '{') {
            i++;
            out->kind = Json::Kind::Object;
            skip_ws();
            if (i < s.size() && s[i] == '}') {
                i++;
                return true;
            }
            for (;;) {
                skip_ws();
                std::string key;
                if (!parse_string(&key)) {
                    return false;
                }
                skip_ws();
                if (i >= s.size() || s[i] != ':') {
                    return fail("expected ':' after an object key");
                }
                i++;
                Json v;
                if (!parse_value(&v)) {
                    return false;
                }
                out->object[key] = std::move(v);
                skip_ws();
                if (i < s.size() && s[i] == ',') {
                    i++;
                    continue;
                }
                if (i < s.size() && s[i] == '}') {
                    i++;
                    return true;
                }
                return fail("expected ',' or '}' in an object");
            }
        }
        if (ch == '[') {
            i++;
            out->kind = Json::Kind::Array;
            skip_ws();
            if (i < s.size() && s[i] == ']') {
                i++;
                return true;
            }
            for (;;) {
                Json v;
                if (!parse_value(&v)) {
                    return false;
                }
                out->array.push_back(std::move(v));
                skip_ws();
                if (i < s.size() && s[i] == ',') {
                    i++;
                    continue;
                }
                if (i < s.size() && s[i] == ']') {
                    i++;
                    return true;
                }
                return fail("expected ',' or ']' in an array");
            }
        }
        if (ch == '"') {
            out->kind = Json::Kind::String;
            return parse_string(&out->str);
        }
        if (lit("true")) {
            out->kind = Json::Kind::Bool;
            out->boolean = true;
            return true;
        }
        if (lit("false")) {
            out->kind = Json::Kind::Bool;
            out->boolean = false;
            return true;
        }
        if (lit("null")) {
            out->kind = Json::Kind::Null;
            return true;
        }
        if (ch == '-' || (ch >= '0' && ch <= '9')) {
            const char* begin = s.c_str() + i;
            char* end = nullptr;
            // strtod is locale-sensitive; nothing calls setlocale, so '.' is the decimal point.
            double d = std::strtod(begin, &end);
            if (end == begin) {
                return fail("expected a number");
            }
            i += size_t(end - begin);
            out->kind = Json::Kind::Number;
            out->number = d;
            return true;
        }
        // Python's json.dump can emit these for non-finite floats; refused, not parsed.
        if (lit("NaN") || lit("Infinity") || lit("-Infinity")) {
            return fail("a non-finite literal (NaN/Infinity): Python wrote it, strict JSON has no "
                        "such value, and this reader will not invent one");
        }
        return fail("not a JSON value");
    }
};

}  // namespace

bool Json::parse(const std::string& text, Json* out, std::string* error) {
    Parser p(text);
    // A UTF-8 BOM in front of a JSON document is legal enough that editors write one.
    if (p.s.compare(0, 3, "\xEF\xBB\xBF") == 0) {
        p.i = 3;
    }
    if (!p.parse_value(out)) {
        *error = p.err;
        return false;
    }
    p.skip_ws();
    if (p.i != p.s.size()) {
        p.fail("trailing text after the document");
        *error = p.err;
        return false;
    }
    return true;
}

bool Json::load(const std::string& path, Json* out, std::string* error) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        *error = "cannot open " + path;
        return false;
    }
    std::string text;
    char buf[1 << 16];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) {
        text.append(buf, n);
    }
    std::fclose(f);
    if (!parse(text, out, error)) {
        *error = path + ": " + *error;
        return false;
    }
    return true;
}

const Json& Json::operator[](const std::string& key) const {
    auto it = object.find(key);
    return it == object.end() ? kNull : it->second;
}

const Json& Json::operator[](size_t i) const {
    return i < array.size() ? array[i] : kNull;
}

size_t Json::size() const {
    if (kind == Kind::Array) {
        return array.size();
    }
    if (kind == Kind::Object) {
        return object.size();
    }
    return 0;
}

bool Json::has(const std::string& key) const {
    return object.find(key) != object.end();
}

uint32_t Json::as_f32_bits() const {
    float f = as_f32();
    uint32_t u;
    std::memcpy(&u, &f, 4);
    return u;
}

}  // namespace testing
}  // namespace tww_engine
