#pragma once

#include <g3log/g3log.hpp>
#include <imgui.h>
#include <iostream>

#include "../Config.h"

namespace OpenNFS {
    struct AppLog {
        ImGuiTextBuffer Buf;
        ImGuiTextFilter Filter;
        ImVector<int> LineOffsets; // Index to lines offset
        bool ScrollToBottom{false};

        void Clear() {
            Buf.clear();
            LineOffsets.clear();
        }

        void AddLine(char const *line) {
            int old_size = Buf.size();
            Buf.append(line);
            for (int const new_size = Buf.size(); old_size < new_size; old_size++)
                if (Buf[old_size] == '\n')
                    LineOffsets.push_back(old_size);
            ScrollToBottom = true;
        }

        void Draw(char const *title, bool *p_open = nullptr) {
            ImGui::SetNextWindowSize(ImVec2(500, 400), ImGuiCond_FirstUseEver);
            if (!ImGui::Begin(title, p_open)) {
                ImGui::End();
                return;
            }
            if (ImGui::Button("Clear"))
                Clear();
            ImGui::SameLine();
            Filter.Draw("Filter", -100.0f);
            ImGui::Separator();
            ImGui::BeginChild("scrolling", ImVec2(0, 0), false, ImGuiWindowFlags_HorizontalScrollbar);
            if (Filter.IsActive()) {
                char const *buf_begin{Buf.begin()};
                char const *line{buf_begin};
                for (int line_no = 0; line != nullptr; line_no++) {
                    char const *line_end{(line_no < LineOffsets.Size) ? buf_begin + LineOffsets[line_no] : nullptr};
                    if (Filter.PassFilter(line, line_end))
                        ImGui::TextUnformatted(line, line_end);
                    line = line_end && line_end[1] ? line_end + 1 : nullptr;
                }
            } else {
                ImGui::TextUnformatted(Buf.begin());
            }
            if (ScrollToBottom)
                ImGui::SetScrollHereY(1.0f);
            ScrollToBottom = false;
            ImGui::EndChild();
            ImGui::End();
        }
    };

    class Logger {
      public:
        AppLog onScreenLog;
        explicit Logger();
    };
} // namespace OpenNFS
